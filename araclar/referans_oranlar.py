"""TCMB EVDS'den haftalık piyasa ortalaması kredi ve mevduat oranlarını alır,
uygulamanın okuduğu oranlar.json dosyasını yazar.

Kullanım:  EVDS_API_KEY=... python3 araclar/referans_oranlar.py oranlar.json

Seri kodları sabit yazılmaz; EVDS'deki veri gruplarının ve serilerin adlarına
göre bulunur. TCMB bir seriyi yeniden adlandırırsa betik hangi adları
bulduğunu yazarak hata verir; eski oranlar.json bozulmaz.
"""

import datetime as dt
import json
import os
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

TABAN = "https://evds3.tcmb.gov.tr/igmevdsms-dis/"


def sade(metin):
    """Karşılaştırma için: küçük harf, Türkçe harfler sade, noktalama boşluk."""
    m = (metin or "").replace("İ", "i").replace("I", "ı").lower()
    m = m.translate(str.maketrans("ıçğöşü", "icgosu"))
    m = unicodedata.normalize("NFKD", m)
    return " ".join("".join(k if k.isalnum() else " " for k in m).split())


def istek(yol, parametreler, anahtar):
    # EVDS parametreleri "?" olmadan doğrudan yolun ardına yazılır:
    # .../serieList/type=json&code=...
    adres = TABAN + yol + "&".join(
        f"{k}={urllib.parse.quote(str(v), safe='.-_')}" for k, v in parametreler.items()
    )
    talep = urllib.request.Request(adres, headers={"key": anahtar})
    try:
        with urllib.request.urlopen(talep, timeout=60) as yanit:
            return json.loads(yanit.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        govde = e.read().decode("utf-8", "replace")[:500]
        raise SystemExit(f"EVDS {e.code}: {adres.split('?')[0]} → {govde}")


# Her kalem: veri grubu adında geçmesi gerekenler, seri adında geçmesi
# gerekenler, geçmemesi gerekenler. Adlar sade() ile karşılaştırılır.
KREDI_GRUBU = ["kredi", "akim", "haftalik"]
MEVDUAT_GRUBU = ["mevduat", "akim", "haftalik"]

KREDILER = {
    "ihtiyac": (["ihtiyac", "tl"], ["kmh dahil", "usd", "eur"]),
    "tasit": (["tasit", "tl"], ["usd", "eur"]),
    "konut": (["konut", "tl"], ["usd", "eur"]),
    "ticari": (["ticari", "tl"], ["usd", "eur", "kmh dahil"]),
}
MEVDUATLAR = {
    "1ay": (["1 aya kadar", "tl"], ["usd", "eur", "toplam"]),
    "3ay": (["3 aya kadar", "tl"], ["usd", "eur", "toplam"]),
    "6ay": (["6 aya kadar", "tl"], ["usd", "eur", "toplam"]),
    "1yil": (["1 yila kadar", "tl"], ["usd", "eur", "toplam"]),
    "1yiluzun": (["1 yil ve", "tl"], ["usd", "eur", "toplam"]),
}


def grup_bul(gruplar, gerekenler):
    adaylar = [
        g for g in gruplar
        if all(k in sade(g.get("DATAGROUP_NAME")) for k in gerekenler)
    ]
    if not adaylar:
        raise SystemExit(
            f"Veri grubu bulunamadı: {gerekenler}. Örnek gruplar: "
            + "; ".join(g.get("DATAGROUP_NAME", "") for g in gruplar[:40])
        )
    # Ağırlıklı ortalama grubunu tercih et.
    adaylar.sort(key=lambda g: "agirlikli" not in sade(g.get("DATAGROUP_NAME")))
    return adaylar[0]


def seri_bul(seriler, gerekenler, olmamalilar):
    adaylar = []
    for s in seriler:
        ad = sade(s.get("SERIE_NAME"))
        if all(k in ad for k in gerekenler) and not any(k in ad for k in olmamalilar):
            adaylar.append(s)
    if not adaylar:
        raise SystemExit(
            f"Seri bulunamadı: {gerekenler}. Gruptaki seriler: "
            + "; ".join(s.get("SERIE_NAME", "") for s in seriler)
        )
    # En kısa ad genellikle ana seridir (alt kırılımlar daha uzun adlıdır).
    adaylar.sort(key=lambda s: len(s.get("SERIE_NAME", "")))
    return adaylar[0]


def son_degerler(kodlar, anahtar, bugun):
    bas = (bugun - dt.timedelta(days=70)).strftime("%d-%m-%Y")
    son = bugun.strftime("%d-%m-%Y")
    veri = istek(
        "",
        {"series": "-".join(kodlar), "startDate": bas, "endDate": son, "type": "json"},
        anahtar,
    )["items"]
    sonuc = {}
    for kod in kodlar:
        alan = kod.replace(".", "_")
        for satir in reversed(veri):
            deger = satir.get(alan)
            if deger not in (None, "", "null"):
                sonuc[kod] = (float(deger), satir.get("Tarih"))
                break
        else:
            raise SystemExit(f"{kod} için son 10 haftada veri yok.")
    return sonuc


def olustur(anahtar, bugun):
    gruplar = istek("datagroups/", {"mode": 0, "code": "", "type": "json"}, anahtar)
    cikti = {
        "kaynak": "TCMB EVDS, bankalarca açılan kredilere ve mevduatlara "
        "uygulanan haftalık ağırlıklı ortalama faiz oranları (akım)",
        "guncelleme": bugun.isoformat(),
    }
    for anahtar_adi, grup_kosulu, kalemler, oran_turu in [
        ("kredi", KREDI_GRUBU, KREDILER, "efektif_yillik"),
        ("mevduat", MEVDUAT_GRUBU, MEVDUATLAR, "bilesik_yillik"),
    ]:
        grup = grup_bul(gruplar, grup_kosulu)
        seriler = istek(
            "serieList/", {"type": "json", "code": grup["DATAGROUP_CODE"]}, anahtar
        )
        secilen = {k: seri_bul(seriler, *v) for k, v in kalemler.items()}
        degerler = son_degerler([s["SERIE_CODE"] for s in secilen.values()], anahtar, bugun)
        cikti[anahtar_adi] = {
            k: {
                "oran": round(degerler[s["SERIE_CODE"]][0], 2),
                "tarih": degerler[s["SERIE_CODE"]][1],
                "tur": oran_turu,
                "seri": s["SERIE_CODE"],
                "ad": s.get("SERIE_NAME"),
            }
            for k, s in secilen.items()
        }
    return cikti


def main():
    anahtar = os.environ.get("EVDS_API_KEY")
    if not anahtar:
        raise SystemExit("EVDS_API_KEY tanımlı değil.")
    hedef = sys.argv[1] if len(sys.argv) > 1 else "oranlar.json"
    cikti = olustur(anahtar, dt.date.today())
    # Makul olmayan değer yayımlanmasın: oranlar %0–%500 arasında olmalı.
    for bolum in ("kredi", "mevduat"):
        for k, v in cikti[bolum].items():
            if not 0 < v["oran"] < 500:
                raise SystemExit(f"{bolum}.{k} oranı makul değil: {v['oran']}")
    with open(hedef, "w", encoding="utf-8") as f:
        json.dump(cikti, f, ensure_ascii=False, indent=2)
    print(json.dumps(cikti, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
