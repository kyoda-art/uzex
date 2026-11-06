"""Asosiy tekshiruvlar: raqamlar to'g'riligi va muhim funksiyalar.

Ishga tushirish:  python -m pytest -q   (yoki: python tests/test_core.py)
Ma'lumot papkasi UZEX_DATA_DIR orqali ko'rsatiladi (standart: ./data/uzex_spot_data).
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import analytics as A  # noqa: E402
from core.charts import make_chart  # noqa: E402
from core.data import ANNULLED, NOT_REALIZED, load  # noqa: E402
from core.export import to_csv_bytes  # noqa: E402
from core.formatter import detect_lang  # noqa: E402
from core.router import route_rules, run_question  # noqa: E402

DS = load()


def test_valid_excludes_not_realized():
    assert not DS.valid["status"].astype(str).isin(NOT_REALIZED).any()
    assert len(DS.valid) == len(DS.deals) - int(DS.deals["status"].astype(str).isin(NOT_REALIZED).sum())


def test_usd_deals_converted_with_rate_of_the_day():
    usd = DS.deals[DS.deals["is_usd"]].dropna(subset=["rate"]).head(200)
    assert len(usd) > 0
    assert np.allclose(usd["amount_uzs"], usd["amount"] * usd["rate"])


def test_uzs_deals_not_converted():
    uzs = DS.deals[~DS.deals["is_usd"]].head(200)
    assert np.allclose(uzs["amount_uzs"], uzs["amount"])


def test_summary_total_equals_sum_of_years():
    total = A.summary(DS)["rows"][1]["value"]
    by_year = A.summary(DS)["rows"][-5:]
    assert math.isclose(total, sum(r["value"] for r in by_year), rel_tol=1e-9)


def test_summary_year_matches_direct_computation():
    df = DS.valid[DS.valid["year"] == 2025]
    rows = A.summary(DS, 2025)["rows"]
    assert rows[0]["value"] == len(df)
    assert math.isclose(rows[1]["value"], df["amount_uzs"].sum(), rel_tol=1e-9)


def test_top_sellers_sorted_descending():
    vals = [r["value"] for r in A.top_sellers(DS, 2025, 10)["rows"]]
    assert vals == sorted(vals, reverse=True) and len(vals) == 10


def test_anomalies_are_really_far_from_median():
    rows = A.anomalies(DS, 2025, n=20)["rows"]
    assert rows, "2025 yilda anomal bitimlar topilishi kerak"
    assert all(abs(r["value"]) >= 0.3 - 1e-9 for r in rows)


def test_anomaly_threshold_is_30_percent_each_side():
    res = A.anomalies(DS, n=50)
    assert res["meta"]["count"] > 0
    assert all(abs(r["value"]) >= 0.3 - 1e-9 for r in res["rows"])


def test_price_trend_within_contract_price_range():
    res = A.price_trend(DS, "хлопок", 2025)
    assert res["rows"]
    head_df = DS.valid[DS.valid["product"].str.lower().str.startswith("хлопок") & (DS.valid["year"] == 2025)]
    lo, hi = head_df["unit_price"].min(), head_df["unit_price"].max()
    for r in res["rows"]:
        assert lo * 0.99 <= r["value"] <= hi * 1.01


def test_resolve_head_handles_declension_and_uzbek():
    assert A.resolve_head(DS, "цена пшеницы") == "пшеница"
    assert A.resolve_head(DS, "хлопка динамика") == "хлопок"
    assert A.resolve_head(DS, "paxta narxi") == "хлопок"
    assert A.resolve_head(DS, "ob-havo qanday") is None


def test_router_rules():
    assert route_rules("Umumiy statistika 2025", DS)[0] == "summary"
    assert route_rules("Dollar kursi 30.10.2026", DS) == ("usd_rate", {"date": "30.10.2026"})
    assert route_rules("ob-havo qanday", DS)[0] is None


def test_out_of_scope_gets_fallback_not_data():
    res = run_question(DS, "Ob-havo qanday?", None)
    assert res["tool"] is None and res["result"] is None


def test_answer_includes_source_footer():
    res = run_question(DS, "Umumiy statistika 2025", None)
    assert "deals_2025.csv" in res["text"]


def test_language_detection():
    assert detect_lang("paxta narxi") == "uz"
    assert detect_lang("цена пшеницы") == "ru"
    assert detect_lang("қалайсиз") == "uz"


def test_csv_export_has_bom_and_header():
    data = to_csv_bytes(run_question(DS, "Eng yirik sotuvchilar 2025", None)["result"])
    assert data.startswith(b"\xef\xbb\xbf")
    assert data.decode("utf-8-sig").splitlines()[0] == "nomi,kod,qiymat,turi,valyuta,izoh"


def test_chart_is_png():
    res = run_question(DS, "Keyingi 3 oy prognoz", None)
    png = make_chart(res["tool"], res["result"], res["lang"])
    assert png is not None and png[:8] == b"\x89PNG\r\n\x1a\n"


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:
                failed += 1
                print("FAIL", name, repr(e))
    print("\nNatija:", "hammasi o'tdi" if not failed else f"{failed} ta xato")
    sys.exit(1 if failed else 0)
