"""
fetch_data.py
Lê a aba 'kiwify_todos_produtos' do Google Sheets via Service Account
e gera data/data.json para o dashboard de recompra.
"""

import os
import json
import re
from datetime import datetime, date
from collections import defaultdict

import gspread
from google.oauth2.service_account import Credentials

# ── Configuração ──────────────────────────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]          # GitHub Secret
SHEET_NAME = "kiwify_todos_produtos"

# Eventos que representam receita real (paid)
PAID_EVENTS = {
    "order_approved",
    "subscription_payment",      # renovação de assinatura
    "subscription_reactivated",  # reativação
}

# ── Autenticação ──────────────────────────────────────────────────────────────
def get_client():
    creds_json = os.environ["GCP_SERVICE_ACCOUNT_JSON"]  # GitHub Secret
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


# ── Helpers ───────────────────────────────────────────────────────────────────
def parse_date(value: str) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_brl(value: str) -> float:
    if not value:
        return 0.0
    cleaned = re.sub(r"[R$\s]", "", str(value)).replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def classify_origin(row: dict) -> str:
    """
    Classifica a origem pelo utm_source, src, sck ou utm_medium.
    Prioridade: utm_source > src > sck
    """
    sources = [
        str(row.get("TrackingParameters_utm_source", "") or "").lower(),
        str(row.get("TrackingParameters_src", "") or "").lower(),
        str(row.get("TrackingParameters_sck", "") or "").lower(),
        str(row.get("TrackingParameters_utm_medium", "") or "").lower(),
    ]
    combined = " ".join(sources)

    if re.search(r"fb|fbads|facebook|meta", combined):
        return "Meta Ads"
    if re.search(r"instagram|ig\b", combined):
        return "Instagram"
    if re.search(r"youtube|yt\b", combined):
        return "YouTube"
    if re.search(r"email|e-mail|mailing", combined):
        return "E-mail"
    if re.search(r"whatsapp|wpp|zap", combined):
        return "WhatsApp"
    if all(s == "" for s in sources):
        return "Sem origem"
    return "Outros"


# ── Processamento principal ────────────────────────────────────────────────────
def process(rows: list[dict]) -> dict:
    # Filtrar apenas linhas pagas
    paid_rows = [
        r for r in rows
        if str(r.get("order_status", "")).strip().lower() == "paid"
        and str(r.get("webhook_event_type", "")).strip().lower() in PAID_EVENTS
    ]

    # Estrutura por email: lista de compras ordenadas
    buyer_purchases: dict[str, list[dict]] = defaultdict(list)

    for r in paid_rows:
        email = str(r.get("Customer_email", "") or "").strip().lower()
        if not email:
            continue

        d = parse_date(str(r.get("Data de Criação", "") or r.get("approved_date", "") or ""))
        if not d:
            continue

        buyer_purchases[email].append({
            "date": d,
            "product": str(r.get("Product_product_name", "") or "").strip(),
            "revenue": parse_brl(str(r.get("Faturamento", "") or r.get("Commissions_charge_amount", ""))),
            "origin": classify_origin(r),
            "event": str(r.get("webhook_event_type", "")).strip().lower(),
        })

    # Ordenar compras por data para cada comprador
    for email in buyer_purchases:
        buyer_purchases[email].sort(key=lambda x: x["date"])

    # ── KPIs globais ──────────────────────────────────────────────────────────
    total_buyers = len(buyer_purchases)

    # Compradores por nº de compras
    buyers_by_count: dict[int, int] = defaultdict(int)
    for purchases in buyer_purchases.values():
        n = len(purchases)
        buyers_by_count[n] += 1

    buyers_1x = buyers_by_count.get(1, 0)
    buyers_2x = buyers_by_count.get(2, 0)
    buyers_3x = buyers_by_count.get(3, 0)
    buyers_4x = buyers_by_count.get(4, 0)
    buyers_4x_plus = sum(v for k, v in buyers_by_count.items() if k >= 4)

    # Recompradores = compraram mais de 1x
    total_rebuyers = sum(1 for p in buyer_purchases.values() if len(p) > 1)
    total_repurchases = sum(len(p) - 1 for p in buyer_purchases.values() if len(p) > 1)

    # LTV médio
    ltv_per_buyer = {
        email: sum(p["revenue"] for p in purchases)
        for email, purchases in buyer_purchases.items()
    }
    avg_ltv = sum(ltv_per_buyer.values()) / total_buyers if total_buyers else 0

    # Tempo médio 1ª → 2ª compra
    days_1_to_2 = []
    days_1_to_last = []
    for purchases in buyer_purchases.values():
        if len(purchases) >= 2:
            delta_1_2 = (purchases[1]["date"] - purchases[0]["date"]).days
            delta_1_last = (purchases[-1]["date"] - purchases[0]["date"]).days
            days_1_to_2.append(delta_1_2)
            days_1_to_last.append(delta_1_last)

    avg_days_1_to_2 = round(sum(days_1_to_2) / len(days_1_to_2)) if days_1_to_2 else 0
    avg_days_1_to_last = round(sum(days_1_to_last) / len(days_1_to_last)) if days_1_to_last else 0

    # Produto com mais recompra
    product_rebuys: dict[str, int] = defaultdict(int)
    for purchases in buyer_purchases.values():
        if len(purchases) > 1:
            for p in purchases[1:]:  # da 2ª compra em diante
                product_rebuys[p["product"]] += 1

    top_rebuy_product = max(product_rebuys, key=product_rebuys.get) if product_rebuys else "—"

    # ── Recompras por mês ─────────────────────────────────────────────────────
    rebuy_by_month: dict[str, int] = defaultdict(int)
    for purchases in buyer_purchases.values():
        for p in purchases[1:]:
            key = p["date"].strftime("%Y-%m")
            rebuy_by_month[key] += 1

    rebuy_by_month_sorted = dict(sorted(rebuy_by_month.items()))

    # ── Recompras por origem ──────────────────────────────────────────────────
    rebuy_by_origin: dict[str, int] = defaultdict(int)
    for purchases in buyer_purchases.values():
        for p in purchases[1:]:
            rebuy_by_origin[p["origin"]] += 1

    # ── Recompras por produto ─────────────────────────────────────────────────
    rebuy_by_product = dict(
        sorted(product_rebuys.items(), key=lambda x: x[1], reverse=True)
    )

    # ── Série temporal de compradores únicos (para filtro de data) ────────────
    buyers_by_month: dict[str, set] = defaultdict(set)
    for email, purchases in buyer_purchases.items():
        for p in purchases:
            key = p["date"].strftime("%Y-%m")
            buyers_by_month[key].add(email)

    buyers_by_month_count = {k: len(v) for k, v in sorted(buyers_by_month.items())}

    # ── Tabela de coorte simplificada (top recompradores) ────────────────────
    top_buyers = sorted(
        [
            {
                "ltv": round(ltv_per_buyer[email], 2),
                "purchases": len(purchases),
                "products": list({p["product"] for p in purchases}),
                "first_date": purchases[0]["date"].isoformat(),
                "last_date": purchases[-1]["date"].isoformat(),
                "origin": purchases[0]["origin"],
            }
            for email, purchases in buyer_purchases.items()
            if len(purchases) > 1
        ],
        key=lambda x: x["purchases"],
        reverse=True,
    )[:50]  # top 50 para não pesar o JSON

    # ── Produtos únicos e origens (para filtros) ──────────────────────────────
    all_products = sorted({
        p["product"]
        for purchases in buyer_purchases.values()
        for p in purchases
        if p["product"]
    })

    all_origins = sorted({
        p["origin"]
        for purchases in buyer_purchases.values()
        for p in purchases
    })

    # ── Montar output ─────────────────────────────────────────────────────────
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "kpis": {
            "total_buyers": total_buyers,
            "buyers_1x": buyers_1x,
            "buyers_2x": buyers_2x,
            "buyers_3x": buyers_3x,
            "buyers_4x_plus": buyers_4x_plus,
            "total_rebuyers": total_rebuyers,
            "total_repurchases": total_repurchases,
            "avg_ltv": round(avg_ltv, 2),
            "avg_days_1_to_2": avg_days_1_to_2,
            "avg_days_1_to_last": avg_days_1_to_last,
            "top_rebuy_product": top_rebuy_product,
        },
        "charts": {
            "rebuy_by_month": rebuy_by_month_sorted,
            "rebuy_by_origin": dict(rebuy_by_origin),
            "rebuy_by_product": rebuy_by_product,
            "buyers_by_month": buyers_by_month_count,
        },
        "filters": {
            "products": all_products,
            "origins": all_origins,
        },
        "top_buyers": top_buyers,
        # Dados granulares para filtragem client-side
        "raw": [
            {
                "email_hash": email,
                "purchases": [
                    {
                        "date": p["date"].isoformat(),
                        "product": p["product"],
                        "revenue": p["revenue"],
                        "origin": p["origin"],
                    }
                    for p in purchases
                ],
                "ltv": round(ltv_per_buyer[email], 2),
                "count": len(purchases),
            }
            for email, purchases in buyer_purchases.items()
        ],
    }


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    print("Conectando ao Google Sheets...")
    client = get_client()
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
    rows = sheet.get_all_records()
    print(f"  {len(rows)} linhas lidas.")

    print("Processando dados...")
    output = process(rows)

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, default=str)

    print(f"  data.json gerado — {len(output['raw'])} compradores processados.")
    print(f"  KPIs: {output['kpis']}")


if __name__ == "__main__":
    main()
