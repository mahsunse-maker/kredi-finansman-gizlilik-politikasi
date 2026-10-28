"""Betiğin EVDS yanıtlarını doğru işlediğini sahte yanıtlarla sınar.
Çalıştırma: python3 -m unittest araclar/test_referans_oranlar.py"""

import datetime as dt
import unittest
from unittest import mock

import referans_oranlar as r

GRUPLAR = [
    {"DATAGROUP_CODE": "bie_x", "DATAGROUP_NAME": "Döviz Kurları"},
    {"DATAGROUP_CODE": "bie_kr", "DATAGROUP_NAME":
        "Kredi Faiz Oranları (Akım) (Haftalık) (Ağırlıklı Ortalama)"},
    {"DATAGROUP_CODE": "bie_mv", "DATAGROUP_NAME":
        "Mevduat Faiz Oranları (Akım) (Haftalık) (Ağırlıklı Ortalama)"},
]
KREDI_SERILERI = [
    {"SERIE_CODE": "K1", "SERIE_NAME": "İhtiyaç (TL Üzerinden Açılan)"},
    {"SERIE_CODE": "K1K", "SERIE_NAME": "İhtiyaç (KMH Dahil, TL Üzerinden Açılan)"},
    {"SERIE_CODE": "K2", "SERIE_NAME": "Taşıt (TL Üzerinden Açılan)"},
    {"SERIE_CODE": "K3", "SERIE_NAME": "Konut (TL Üzerinden Açılan)"},
    {"SERIE_CODE": "K4", "SERIE_NAME": "Ticari (TL Üzerinden Açılan)"},
    {"SERIE_CODE": "K4U", "SERIE_NAME": "Ticari (USD Üzerinden Açılan)"},
]
MEVDUAT_SERILERI = [
    {"SERIE_CODE": "M1", "SERIE_NAME": "1 Aya Kadar Vadeli (TL)"},
    {"SERIE_CODE": "M3", "SERIE_NAME": "3 Aya Kadar Vadeli (TL)"},
    {"SERIE_CODE": "M6", "SERIE_NAME": "6 Aya Kadar Vadeli (TL)"},
    {"SERIE_CODE": "M12", "SERIE_NAME": "1 Yıla Kadar Vadeli (TL)"},
    {"SERIE_CODE": "M13", "SERIE_NAME": "1 Yıl ve Daha Uzun Vadeli (TL)"},
    {"SERIE_CODE": "MU", "SERIE_NAME": "1 Aya Kadar Vadeli (USD)"},
]


def sahte(yol, prm, anahtar):
    if yol.startswith("datagroups"):
        return GRUPLAR
    if yol.startswith("serieList"):
        return KREDI_SERILERI if prm["code"] == "bie_kr" else MEVDUAT_SERILERI
    kodlar = prm["series"].split("-")
    return {"items": [
        {"Tarih": "16-10-2026", **{k: "40.0" for k in kodlar}},
        {"Tarih": "23-10-2026", **{k: str(40 + i) for i, k in enumerate(kodlar)},
         "K3": None},
    ]}


class Test(unittest.TestCase):
    def test_seriler_adlarindan_bulunur(self):
        with mock.patch.object(r, "istek", sahte):
            c = r.olustur("x", dt.date(2026, 10, 28))
        self.assertEqual(c["kredi"]["ihtiyac"]["seri"], "K1")
        self.assertEqual(c["kredi"]["ticari"]["seri"], "K4")
        self.assertEqual(c["mevduat"]["1yiluzun"]["seri"], "M13")
        self.assertEqual(c["kredi"]["ihtiyac"]["oran"], 40)
        self.assertEqual(c["kredi"]["ihtiyac"]["tarih"], "23-10-2026")
        # Son haftada boş olan seri için bir önceki değer alınır.
        self.assertEqual(c["kredi"]["konut"]["tarih"], "16-10-2026")
        self.assertEqual(c["kredi"]["konut"]["tur"], "efektif_yillik")
        self.assertEqual(c["mevduat"]["3ay"]["tur"], "bilesik_yillik")

    def test_bulunamayan_seri_aciklamayla_durur(self):
        eksik = [s for s in KREDI_SERILERI if s["SERIE_CODE"] != "K2"]
        with self.assertRaises(SystemExit) as h:
            r.seri_bul(eksik, *r.KREDILER["tasit"])
        self.assertIn("İhtiyaç", str(h.exception))

    def test_turkce_sadelestirme(self):
        self.assertEqual(r.sade("İhtiyaç (TL Üzerinden)"), "ihtiyac tl uzerinden")
        self.assertEqual(r.sade("1 YIL VE DAHA UZUN"), "1 yil ve daha uzun")


if __name__ == "__main__":
    unittest.main()
