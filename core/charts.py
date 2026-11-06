"""Grafiklar (PNG). matplotlib faqat kerak bo'lganda import qilinadi (xotirani tejash uchun)."""
from __future__ import annotations

import io

from .formatter import title_text


def _plain(title: str) -> str:
    """Grafik shriftida emoji yo'q: faqat matn belgilari qoldiriladi."""
    return "".join(ch for ch in title if ord(ch) < 0x2000 or 0x0400 <= ord(ch) <= 0x04FF or 0x2010 <= ord(ch) <= 0x2027).strip()

CHART_TOOLS = {
    "summary", "price_trend", "forecast",
    "top_sellers", "top_buyers", "top_products", "top_regions", "top_brokers", "trade_network",
}


def make_chart(tool: str, result: dict, lang: str) -> bytes | None:
    if tool not in CHART_TOOLS:
        return None
    rows = [r for r in (result.get("rows") or []) if r.get("value") is not None]
    if not rows and not (result.get("meta") or {}).get("monthly"):
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=100)
    try:
        if tool == "summary":
            monthly = (result.get("meta") or {}).get("monthly") or []
            if monthly:  # yil tanlangan: oylik hajm
                ax.bar([m for m, _ in monthly], [v / 1e9 for _, v in monthly], color="#2b6cb0")
                plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
            else:  # yil tanlanmagan: yillik hajm
                yrs = [r for r in rows if r.get("label") is None and r.get("vtype") == "uzs"]
                if not yrs:
                    return None
                ax.bar([str(r["name"]) for r in yrs], [r["value"] / 1e9 for r in yrs], color="#2b6cb0")
            ax.set_ylabel("mlrd so'm" if lang == "uz" else "млрд сум")
        elif tool == "price_trend":
            ax.plot([str(r["name"]) for r in rows], [r["value"] for r in rows], marker="o", color="#2b6cb0")
            ax.set_ylabel(rows[0].get("cur") or "")
            plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
        elif tool == "forecast":
            names = [str(r["name"]) for r in rows]
            vals = [r["value"] / 1e9 for r in rows]
            colors = ["#718096" if r.get("tag") == "actual" else "#dd6b20" for r in rows]
            ax.bar(names, vals, color=colors)
            ax.set_ylabel("mlrd so'm" if lang == "uz" else "млрд сум")
            plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
        else:  # top ro'yxatlar: gorizontal ustunlar
            top = rows[:10][::-1]
            labels = [(str(r["name"]) if len(str(r["name"])) <= 34 else str(r["name"])[:31] + "...") for r in top]
            vals = [r["value"] / 1e9 for r in top]
            ax.barh(labels, vals, color="#2b6cb0")
            ax.set_xlabel("mlrd so'm" if lang == "uz" else "млрд сум")
        ax.set_title(_plain(title_text(tool, result, lang)), fontsize=10)
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    finally:
        plt.close(fig)
