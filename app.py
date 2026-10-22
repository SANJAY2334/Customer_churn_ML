"""Streamlit dashboard for the locally trained telecom churn models."""
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import streamlit as st

from src.config import ACTIVE_MODEL_NAME, RISK_CONFIG, get_risk_tier
from src.predictor import (
    load_churn_model,
    predict_customer_churn,
    analyze_feature_contributions,
    calculate_financial_impact,
    generate_business_recommendations
)
from src.batch_processor import process_batch_csv
from src.prioritization import rank_customers, filter_customer_cohort
from src.simulator import simulate_retention_campaign

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "Data" / "processed_data.csv"
ARTIFACT_PATH = ROOT / "Models" / "churn_models.joblib"

st.set_page_config(page_title="Customer Churn Prediction", page_icon="📡", layout="wide")
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
  .stApp { background: #f5f7fb; color: #172b3a; font-family: 'DM Sans', sans-serif; }
  [data-testid="stSidebar"] { background: #fff; border-right: 1px solid #e4e9f1; }
  [data-testid="stSidebar"] > div:first-child { padding-top: 1.5rem; }
  .brand-row { display: flex; align-items: center; gap: 11px; padding: 0 0 20px; margin-bottom: 15px; border-bottom: 1px solid #e8edf3; }
  .brand-icon { width: 38px; height: 38px; display: grid; place-items: center; color: white; font: 800 1rem 'Manrope',sans-serif; border-radius: 12px; background: linear-gradient(145deg,#087f82,#28b39b); box-shadow: 0 5px 12px rgba(8,127,130,.2); }
  .brand-name { font: 800 .92rem 'Manrope',sans-serif; color: #18374c; }
  .brand-sub { font-size: .65rem; color: #73879a; letter-spacing: .1em; margin-top: 2px; }
  [data-testid="stSidebar"] [data-testid="stRadio"] label { font-weight: 600; border-radius: 10px; }
  [data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background: #eff7f6; }
  [data-testid="stMetric"] { background: #fff; border: 1px solid #e4e9f1; padding: 18px 20px; border-radius: 16px; box-shadow: 0 5px 18px rgba(24,52,76,.035); }
  [data-testid="stMetricLabel"] { color: #607386; font-size: .86rem; }
  [data-testid="stMetricValue"] { color: #17354b; font-family: 'Manrope', sans-serif; font-weight: 800; }
  .block-container { max-width: 1260px; padding-top: 2rem; padding-bottom: 4rem; }
  h1, h2, h3, h4 { font-family: 'Manrope', sans-serif !important; color: #17354b; letter-spacing: -.035em; }
  h2 { margin-top: 1.6rem !important; }
  .hero { display: grid; grid-template-columns: minmax(0,1.65fr) minmax(220px,.75fr); align-items: center; gap: 32px; padding: 40px 44px; border-radius: 24px; color: white; background: radial-gradient(circle at 76% 8%, rgba(78,226,196,.24), transparent 25%), linear-gradient(118deg,#10263a 0%,#123e55 52%,#087f7a 100%); margin-bottom: 28px; box-shadow: 0 22px 55px rgba(13,63,82,.19); overflow: hidden; }
  .hero-art { min-height: 190px; border: 1px solid rgba(255,255,255,.2); border-radius: 20px; padding: 22px; background: linear-gradient(145deg,rgba(255,255,255,.14),rgba(255,255,255,.045)); backdrop-filter: blur(8px); }
  .hero-art-label { color: #b8d7df; font-size: .72rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
  .hero-dial { width: 124px; height: 124px; display: grid; place-items: center; margin: 15px auto 10px; border-radius: 50%; background: conic-gradient(#58e0c5 0deg var(--angle),rgba(255,255,255,.15) var(--angle) 360deg); }
  .hero-dial span { width: 99px; height: 99px; display: grid; place-items: center; border-radius: 50%; background: #164356; color: #fff; font: 800 1.75rem 'Manrope',sans-serif; }
  .hero-art-note { color: #d0e5e9; font-size: .84rem; }
  .hero .eyebrow { display: inline-block; padding: 6px 11px; border-radius: 999px; background: rgba(255,255,255,.12); color: #d2f6ef; font-size: .75rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 15px; }
  .hero h1 { color: white; margin: 0 0 11px; font-size: clamp(2rem,4vw,3.1rem); line-height: 1.08; }
  .hero p { color: #d8eaf0; margin: 0; font-size: 1.05rem; max-width: 690px; line-height: 1.65; }
  .section-kicker { color: #15837f; font-size: .75rem; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; margin-bottom: 5px; }
  .page-header { margin: 1.2rem 0 1.55rem; }
  .page-header h1 { margin: .25rem 0 .45rem; font-size: clamp(1.8rem,3vw,2.45rem); }
  .page-header p { color: #63788c; margin: 0; max-width: 780px; font-size: 1rem; line-height: 1.6; }
  .form-note { color: #62758a; font-size: .94rem; margin: -.25rem 0 1rem; }
  .result-card { padding: 22px 25px; margin: 22px 0 12px; border-radius: 18px; border: 1px solid; }
  .result-card h2 { margin: 5px 0 7px !important; font-size: 1.55rem; }
  .result-card p { margin: 0; color: #53687a; }
  .result-card.risk { background: #fff7f2; border-color: #f4d3c2; }
  .result-card.risk .section-kicker { color: #ba6338; }
  .result-card.stay { background: #effaf7; border-color: #c9e9dd; }
  .result-card.stay .section-kicker { color: #14816e; }
  [data-testid="stVerticalBlockBorderWrapper"] { border-color: #e3e9f1 !important; border-radius: 18px !important; background: rgba(255,255,255,.72); }
  .stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] { border: 0; border-radius: 12px; background: linear-gradient(100deg,#087f82,#11a395); font-weight: 700; min-height: 3rem; box-shadow: 0 7px 15px rgba(8,127,130,.18); }
  .stButton button[kind="primary"]:hover, .stFormSubmitButton button[kind="primary"]:hover { background: #076d70; border: 0; }
  [data-testid="stSelectbox"] label, [data-testid="stNumberInput"] label { color: #30495f; font-weight: 600; }
  [data-testid="stAlert"] { border-radius: 14px; }
  .muted { color: #526477; }
  @media (max-width: 700px) { .hero { grid-template-columns: 1fr; padding: 28px 24px; } .hero-art { min-height: auto; } .block-container { padding-top: 1rem; } }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_data(path: str, modified: float):
    return pd.read_csv(path)


@st.cache_resource
def load_artifact(path: str, modified: float):
    return joblib.load(path)


def find_column(df, candidates):
    normalized = {"".join(ch for ch in str(c).lower() if ch.isalnum()): c for c in df.columns}
    for candidate in candidates:
        key = "".join(ch for ch in candidate.lower() if ch.isalnum())
        if key in normalized:
            return normalized[key]
    return None


def target_values(series):
    if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
        return series.astype(int)
    values = series.astype(str).str.strip().str.lower()
    positive = values.isin(["yes", "true", "1", "churn", "churned"])
    negative = values.isin(["no", "false", "0", "stay", "stayed", "not churned"])
    if not (positive | negative).all():
        raise ValueError("The target contains values that cannot be interpreted as churn/stay.")
    return positive.astype(int)


def numeric_series(df, column):
    return pd.to_numeric(df[column], errors="coerce")


def contract_values(frame):
    """Return raw or reconstructed IBM Telco contract categories."""
    contract_column = find_column(frame, ["Contract"])
    if contract_column:
        return frame[contract_column].fillna("Unknown").astype(str)
    one_year = next((c for c in frame.columns if str(c).strip().lower() == "contract_one year".lower()), None)
    two_year = next((c for c in frame.columns if str(c).strip().lower() == "contract_two year".lower()), None)
    if not one_year or not two_year:
        return None

    def active(series):
        if pd.api.types.is_bool_dtype(series.dtype):
            return series.fillna(False)
        return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})

    result = pd.Series("Month-to-month", index=frame.index, dtype="object")
    result.loc[active(frame[one_year])] = "One year"
    result.loc[active(frame[two_year])] = "Two year"
    return result


def flag_values(series):
    if pd.api.types.is_bool_dtype(series.dtype):
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def internet_service_values(frame):
    fiber_col = next((c for c in frame.columns if str(c).strip().lower() == "internet service_fiber optic"), None)
    no_col = next((c for c in frame.columns if str(c).strip().lower() == "internet service_no"), None)
    if fiber_col is None or no_col is None:
        return None
    labels = pd.Series("DSL", index=frame.index, dtype="object")
    labels.loc[flag_values(frame[fiber_col])] = "Fiber optic"
    labels.loc[flag_values(frame[no_col])] = "No internet"
    return labels


def churn_rate_by_group(values, target, name):
    frame = pd.DataFrame({"group": values, "churn": target}).dropna(subset=["group"])
    summary = frame.groupby("group", observed=True, sort=False)["churn"].agg(
        customers="size", churn_rate="mean").reset_index()
    summary["churn_rate"] *= 100
    summary = summary.rename(columns={"group": name})
    return summary


def tenure_bands(frame, tenure_column):
    tenure = numeric_series(frame, tenure_column)
    return pd.cut(tenure, bins=[-1, 12, 24, 36, 48, 60, np.inf],
                  labels=["0-12", "13-24", "25-36", "37-48", "49-60", "61+"],
                  include_lowest=True, ordered=True)


def style_axis(ax, *, horizontal=False):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#dbe4ed")
    ax.grid(axis="x" if horizontal else "y", color="#e8eef4", linewidth=.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors="#536a7e", labelsize=9)
    ax.xaxis.label.set_color("#536a7e")
    ax.yaxis.label.set_color("#536a7e")


def page_header(eyebrow, title, description):
    st.markdown(f"<div class='page-header'><div class='section-kicker'>{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>",
                unsafe_allow_html=True)


def prepare_uploaded_customers(uploaded_df, feature_columns, training_df):
    """Match an uploaded CSV to trained features, ignoring extra label/ID columns."""
    def key(name):
        return "".join(ch for ch in str(name).lower() if ch.isalnum())

    lookup = {}
    for source_name in uploaded_df.columns:
        normalized_name = key(source_name)
        if normalized_name in lookup:
            raise ValueError(f"The file has duplicate columns that look alike: {source_name}")
        lookup[normalized_name] = source_name
    missing = [feature for feature in feature_columns if key(feature) not in lookup]
    if missing:
        shown = ", ".join(missing[:10])
        more = f" (and {len(missing) - 10} more)" if len(missing) > 10 else ""
        raise ValueError(f"This file is missing required customer details: {shown}{more}. Download the CSV template below to see the required columns.")

    features = pd.DataFrame(index=uploaded_df.index)
    for feature in feature_columns:
        values = uploaded_df[lookup[key(feature)]].replace(r"^\s*$", np.nan, regex=True)
        if pd.api.types.is_bool_dtype(training_df[feature].dtype):
            def parse_boolean(value):
                if pd.isna(value):
                    return np.nan
                if isinstance(value, (bool, np.bool_)):
                    return bool(value)
                normalized_value = str(value).strip().lower()
                if normalized_value in {"true", "yes", "1", "1.0"}:
                    return True
                if normalized_value in {"false", "no", "0", "0.0"}:
                    return False
                return None
            converted = values.map(parse_boolean)
            invalid = values.notna() & converted.isna()
            if invalid.any():
                raise ValueError(f"Column '{feature}' must use Yes/No or True/False values.")
            features[feature] = converted.astype(float)
        elif pd.api.types.is_numeric_dtype(training_df[feature].dtype):
            converted = pd.to_numeric(values, errors="coerce")
            invalid = values.notna() & converted.isna()
            if invalid.any():
                raise ValueError(f"Column '{feature}' contains values that are not numbers.")
            features[feature] = converted
        else:
            features[feature] = values
    return features


def customer_form_sections(features, frame):
    """Return beginner-friendly form groups mapped to the dataset's encoded columns."""
    remaining = set(features)
    sections = []

    def grouped(section, label, expected, options):
        if all(name in remaining for name in expected):
            sections.append((section, "choice", label, options))
            remaining.difference_update(expected)

    grouped("Services", "Phone line setup", ["Phone Service_Yes", "Multiple Lines_No phone service", "Multiple Lines_Yes"], {
        "No phone service": {"Phone Service_Yes": False, "Multiple Lines_No phone service": True, "Multiple Lines_Yes": False},
        "One phone line": {"Phone Service_Yes": True, "Multiple Lines_No phone service": False, "Multiple Lines_Yes": False},
        "Multiple phone lines": {"Phone Service_Yes": True, "Multiple Lines_No phone service": False, "Multiple Lines_Yes": True},
    })
    grouped("Services", "Internet service", ["Internet Service_Fiber optic", "Internet Service_No"], {
        "DSL": {"Internet Service_Fiber optic": False, "Internet Service_No": False},
        "Fiber optic": {"Internet Service_Fiber optic": True, "Internet Service_No": False},
        "No internet service": {"Internet Service_Fiber optic": False, "Internet Service_No": True},
    })
    service_options = {"Yes": (False, True), "No": (False, False)}
    for service, title in [("Online Security", "Online security"), ("Online Backup", "Online backup"),
                           ("Device Protection", "Device protection"), ("Tech Support", "Tech support"),
                           ("Streaming TV", "TV streaming"), ("Streaming Movies", "Movie streaming")]:
        no_net, yes = f"{service}_No internet service", f"{service}_Yes"
        grouped("Services", title, [no_net, yes], {
            label: {no_net: flags[0], yes: flags[1]} for label, flags in service_options.items()
        })
    grouped("Account and billing", "Contract length", ["Contract_One year", "Contract_Two year"], {
        "Month to month": {"Contract_One year": False, "Contract_Two year": False},
        "One year": {"Contract_One year": True, "Contract_Two year": False},
        "Two years": {"Contract_One year": False, "Contract_Two year": True},
    })
    grouped("Account and billing", "Payment method", ["Payment Method_Credit card (automatic)",
             "Payment Method_Electronic check", "Payment Method_Mailed check"], {
        "Bank transfer (automatic)": {"Payment Method_Credit card (automatic)": False,
                                      "Payment Method_Electronic check": False, "Payment Method_Mailed check": False},
        "Credit card (automatic)": {"Payment Method_Credit card (automatic)": True,
                                    "Payment Method_Electronic check": False, "Payment Method_Mailed check": False},
        "Electronic check": {"Payment Method_Credit card (automatic)": False,
                             "Payment Method_Electronic check": True, "Payment Method_Mailed check": False},
        "Mailed check": {"Payment Method_Credit card (automatic)": False,
                         "Payment Method_Electronic check": False, "Payment Method_Mailed check": True},
    })

    friendly = {
        "Gender_Male": ("Customer details", "Gender", {"Female": False, "Male": True}),
        "Senior Citizen_Yes": ("Customer details", "Is the customer a senior citizen?", {"No": False, "Yes": True}),
        "Partner_Yes": ("Customer details", "Does the customer have a partner?", {"No": False, "Yes": True}),
        "Dependents_Yes": ("Customer details", "Does the customer have dependents?", {"No": False, "Yes": True}),
        "Paperless Billing_Yes": ("Account and billing", "Paperless billing", {"No": False, "Yes": True}),
    }
    numbers = {"Tenure Months": "Time with company (months)",
               "Monthly Charges": "Monthly bill ($)", "Total Charges": "Total billed so far ($)"}
    for feature in features:
        if feature not in remaining:
            continue
        if feature in friendly:
            section, label, options = friendly[feature]
            sections.append((section, "single_choice", (feature, label), options))
        elif feature in numbers and pd.api.types.is_numeric_dtype(frame[feature].dtype):
            sections.append(("Account and billing", "number", (feature, numbers[feature]), None))
        elif pd.api.types.is_bool_dtype(frame[feature].dtype):
            sections.append(("Other details", "single_choice", (feature, str(feature).replace("_", " ")),
                             {"No": False, "Yes": True}))
        else:
            sections.append(("Other details", "generic", (feature, str(feature).replace("_", " ")), None))
    order = ["Customer details", "Account and billing", "Services", "Other details"]
    return [item for section in order for item in sections if item[0] == section]


if not DATA_PATH.is_file():
    st.error(f"Dataset not found at `{DATA_PATH}`. Put the processed CSV in the Data folder.")
    st.stop()

df = load_data(str(DATA_PATH), DATA_PATH.stat().st_mtime)
target_col = find_column(df, ["Churn Value", "Churn", "Churn Label", "Exited", "Is Churn"])
if target_col is None:
    churn_candidates = [c for c in df.columns if "churn" in str(c).lower()]
    if len(churn_candidates) == 1:
        target_col = churn_candidates[0]
if target_col is None:
    st.error("Could not identify the target column. Expected a column such as Churn Value or Churn Label.")
    st.stop()
try:
    y_all = target_values(df[target_col])
except ValueError as error:
    st.error(str(error))
    st.stop()

st.sidebar.markdown("<div class='brand-row'><div class='brand-icon'>C</div><div><div class='brand-name'>Churn Insights</div><div class='brand-sub'>TELECOM ANALYTICS</div></div></div>", unsafe_allow_html=True)
page_labels = {
    "◈  Dashboard": "Overview",
    "◎  Predict a customer": "Predict a customer",
    "⇧  Score a customer list": "Upload a dataset",
    "▤  Model performance": "Model results",
    "⌘  Explore the data": "Explore the data",
}
selected_page = st.sidebar.radio("Navigation", list(page_labels))
page = page_labels[selected_page]
st.sidebar.caption("Use the sections above to explore the data or make a prediction.")

if page == "Overview":
    total = len(df)
    churned = int(y_all.sum())
    stayed = total - churned
    churn_rate = churned / total if total else 0.0
    angle = churn_rate * 360
    st.markdown(f"""
    <div class='hero'>
      <div class='hero-copy'>
        <div class='eyebrow'>CUSTOMER INTELLIGENCE</div>
        <h1>Customer Churn Prediction</h1>
        <p>Explore customer retention, compare churn across contracts and tenure, and score individual customers with the trained model.</p>
      </div>
      <div class='hero-art'>
        <div class='hero-art-label'>OVERALL CHURN RATE</div>
        <div class='hero-dial' style='--angle:{angle:.1f}deg'><span>{churn_rate:.1%}</span></div>
        <div class='hero-art-note'>{churned:,} of {total:,} customers left</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total customers", f"{total:,}")
    k2.metric("Customers who churned", f"{churned:,}")
    k3.metric("Customers who stayed", f"{stayed:,}")
    k4.metric("Overall churn rate", f"{churn_rate:.1%}")

    st.markdown("<div class='section-kicker'>CUSTOMER TRENDS</div>", unsafe_allow_html=True)
    st.subheader("Who leaves, and when?")
    left, right = st.columns(2, gap="large")
    with left:
        with st.container(border=True):
            st.markdown("### Churn distribution")
            fig, ax = plt.subplots(figsize=(5.2, 3.5))
            ax.pie([stayed, churned], colors=["#1b9a91", "#e2a65e"], startangle=90,
                   counterclock=False, wedgeprops={"width": .34, "edgecolor": "white", "linewidth": 3})
            ax.text(0, .05, f"{total:,}", ha="center", va="center", fontsize=22, weight="bold", color="#17354b")
            ax.text(0, -.18, "customers", ha="center", va="center", fontsize=9, color="#62758a")
            ax.legend([f"Stayed  {stayed:,}", f"Churned  {churned:,}"], loc="center left",
                      bbox_to_anchor=(.88, .5), frameon=False, labelspacing=1.35)
            ax.set(aspect="equal")
            fig.tight_layout()
            st.pyplot(fig, width="stretch")
            plt.close(fig)
    with right:
        with st.container(border=True):
            st.markdown("### Churn by contract type")
            contracts = contract_values(df)
            if contracts is None:
                st.info("A contract column is not available in this processed dataset.")
            else:
                contract_summary = churn_rate_by_group(contracts, y_all, "Contract")
                fig, ax = plt.subplots(figsize=(5.2, 3.5))
                bars = ax.barh(contract_summary["Contract"], contract_summary["churn_rate"],
                               color=["#087f82", "#2b9d99", "#75c7b7"][:len(contract_summary)], height=.58)
                for bar, rate, count in zip(bars, contract_summary["churn_rate"], contract_summary["customers"]):
                    ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
                            f"{rate:.1f}%  ({count:,})", va="center", fontsize=8.5, color="#425a6f")
                ax.set_xlabel("Customers who churned (%)")
                ax.set_xlim(0, max(100, float(contract_summary["churn_rate"].max()) * 1.55))
                style_axis(ax, horizontal=True)
                fig.tight_layout()
                st.pyplot(fig, width="stretch")
                plt.close(fig)

    left, right = st.columns([1, 1.15], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("### Churn by customer tenure")
            tenure_column = find_column(df, ["Tenure Months", "Tenure", "tenure"])
            if tenure_column:
                tenure_summary = churn_rate_by_group(tenure_bands(df, tenure_column), y_all, "Tenure")
                fig, ax = plt.subplots(figsize=(6.2, 3.8))
                x = np.arange(len(tenure_summary))
                ax.plot(x, tenure_summary["churn_rate"], marker="o", markersize=7,
                        linewidth=2.7, color="#078b87")
                ax.fill_between(x, tenure_summary["churn_rate"].to_numpy(), color="#078b87", alpha=.12)
                ax.set_xticks(x, tenure_summary["Tenure"].astype(str))
                ax.set_xlabel("Time with company (months)")
                ax.set_ylabel("Customers who churned (%)")
                ax.set_ylim(bottom=0)
                style_axis(ax)
                fig.tight_layout()
                st.pyplot(fig, width="stretch")
                plt.close(fig)
            else:
                st.info("A tenure column is not available in this dataset.")
    with right:
        with st.container(border=True):
            st.markdown("### Model performance summary")
            if ARTIFACT_PATH.is_file():
                try:
                    dashboard_artifact = load_artifact(str(ARTIFACT_PATH), ARTIFACT_PATH.stat().st_mtime)
                    best_name = dashboard_artifact["best_model"]
                    best_metrics = dashboard_artifact["metrics"][best_name]
                    st.caption(f"Selected model: **{best_name}** (highest test-set F1-score)")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Accuracy", f"{best_metrics['Accuracy']:.3f}")
                    m2.metric("Recall", f"{best_metrics['Recall']:.3f}")
                    auc = best_metrics.get("ROC-AUC")
                    m3.metric("ROC-AUC", f"{auc:.3f}" if auc is not None else "N/A")
                    all_scores = pd.DataFrame(dashboard_artifact["metrics"]).T
                    st.dataframe(all_scores[["Accuracy", "Precision", "Recall", "F1-score"]].style.format("{:.3f}"),
                                 width="stretch", height=165)
                    st.caption("Measured on the held-out test split; these scores are not predictions for future data.")
                except Exception as error:
                    st.warning(f"Could not load saved model performance: {error}")
            else:
                st.info("Train the models once with `python train_model.py` to show measured results.")

    # Phase 2: Decision Support, Portfolio Risk Intelligence & Retention Prioritization
    st.markdown("---")
    st.markdown("<div class='section-kicker'>BUSINESS INTELLIGENCE & DECISION SUPPORT</div>", unsafe_allow_html=True)
    st.subheader("Portfolio Risk Intelligence & Retention Prioritization")
    st.caption("Strategic analytics, segment risk exposure, multi-criteria customer ranking, and campaign scenario simulation.")

    if ARTIFACT_PATH.is_file():
        try:
            active_model_inst = load_churn_model(str(ARTIFACT_PATH))
            active_thresh = getattr(active_model_inst, "threshold_", 0.3236)
            active_m_name = getattr(active_model_inst, "model_name_", "XGBoost")

            # Score historical dataset with active model
            scored_df, batch_summary = process_batch_csv(df, active_model_inst, threshold=active_thresh)

            # Executive KPIs
            pk1, pk2, pk3, pk4 = st.columns(4)
            pk1.metric("Customers Scored", f"{len(scored_df):,}", help="Total customers evaluated with the active model.")
            pk2.metric("Predicted High-Risk", f"{batch_summary['high_risk_count']:,} ({batch_summary['high_risk_count']/len(scored_df):.1%})", help="Customers with estimated churn probability > 60%.")
            pk3.metric("Urgent Retention Priority", f"{batch_summary['urgent_priority_count']:,}", help="Top-tier customers with urgent risk and high value.")
            pk4.metric("Revenue at Risk", f"${batch_summary['total_revenue_at_risk_$']:,.0f}", help="Total estimated revenue exposure across the scored cohort.")

            st.caption(f"Active Model: **{active_m_name}** | Decision Threshold: **{active_thresh:.4f}** | Risk Tiers: Low (≤{RISK_CONFIG['low_threshold']:.0%}), Medium ({RISK_CONFIG['low_threshold']:.0%}-{RISK_CONFIG['medium_threshold']:.0%}), High (>{RISK_CONFIG['medium_threshold']:.0%})")

            # Risk Distribution & Segment Comparison
            dist_left, dist_right = st.columns(2, gap="large")
            with dist_left:
                with st.container(border=True):
                    st.markdown("### Churn Probability Distribution")
                    st.caption("Predicted probability spread across the customer base with decision threshold.")
                    fig_dist, ax_dist = plt.subplots(figsize=(6, 3.8))
                    probs_all = scored_df['Churn_Probability_%'] / 100.0
                    sns.histplot(probs_all, bins=25, kde=True, color="#087f82", ax=ax_dist, stat="density", alpha=0.55)
                    ax_dist.axvline(active_thresh, color="#ef4444", linestyle="--", linewidth=2.0, label=f"Threshold ({active_thresh:.3f})")
                    ax_dist.axvline(RISK_CONFIG['low_threshold'], color="#22c55e", linestyle=":", linewidth=1.5, label="Low Risk (≤30%)")
                    ax_dist.axvline(RISK_CONFIG['medium_threshold'], color="#f59e0b", linestyle=":", linewidth=1.5, label="Medium Risk (≤60%)")
                    ax_dist.set_xlabel("Predicted Churn Probability")
                    ax_dist.set_ylabel("Density")
                    ax_dist.set_xlim(0.0, 1.0)
                    ax_dist.legend(loc="upper right", frameon=False, fontsize=8)
                    style_axis(ax_dist)
                    fig_dist.tight_layout()
                    st.pyplot(fig_dist, width="stretch")
                    plt.close(fig_dist)

            with dist_right:
                with st.container(border=True):
                    st.markdown("### Historical Churn vs. Model Predicted Risk")
                    st.caption("Clear comparison distinguishing observed historical churn from model predictions.")
                    contracts_seg = contract_values(df)
                    if contracts_seg is not None:
                        seg_df = pd.DataFrame({
                            "Contract": contracts_seg,
                            "Observed_Churn": y_all,
                            "Predicted_Prob": probs_all
                        })
                        comp_summary = seg_df.groupby("Contract", observed=True).agg(
                            Customers=("Observed_Churn", "size"),
                            Historical_Churn_Rate=("Observed_Churn", lambda s: s.mean() * 100),
                            Model_Predicted_Risk=("Predicted_Prob", lambda s: s.mean() * 100)
                        ).reset_index()

                        fig_comp, ax_comp = plt.subplots(figsize=(6, 3.8))
                        x_idx = np.arange(len(comp_summary))
                        width_b = 0.35
                        ax_comp.bar(x_idx - width_b/2, comp_summary["Historical_Churn_Rate"], width=width_b, label="Observed Churn (%)", color="#17354b")
                        ax_comp.bar(x_idx + width_b/2, comp_summary["Model_Predicted_Risk"], width=width_b, label="Model Predicted Risk (%)", color="#087f82")
                        ax_comp.set_xticks(x_idx)
                        ax_comp.set_xticklabels(comp_summary["Contract"])
                        ax_comp.set_ylabel("Percentage (%)")
                        ax_comp.set_ylim(0, max(80, comp_summary[["Historical_Churn_Rate", "Model_Predicted_Risk"]].max().max() * 1.25))
                        ax_comp.legend(loc="upper right", frameon=False, fontsize=8)
                        style_axis(ax_comp)
                        fig_comp.tight_layout()
                        st.pyplot(fig_comp, width="stretch")
                        plt.close(fig_comp)
                    else:
                        st.info("Contract data unavailable for segment comparison.")

            # Customer Retention Prioritization Table
            with st.container(border=True):
                st.markdown("### Customer Retention Prioritization Table")
                st.caption("Multi-criteria ranked customer queue combining predicted churn risk and customer lifetime value (CLV).")

                # Filter controls
                f_col1, f_col2, f_col3, f_col4 = st.columns(4)
                with f_col1:
                    filter_tiers = st.multiselect("Priority Tier", ["Urgent", "High", "Medium", "Low"], default=["Urgent", "High"])
                with f_col2:
                    filter_risks = st.multiselect("Risk Category", ["High Risk", "Medium Risk", "Low Risk"], default=["High Risk", "Medium Risk"])
                with f_col3:
                    all_contracts = list(contract_values(df).unique()) if contract_values(df) is not None else []
                    filter_contracts = st.multiselect("Contract Type", all_contracts, default=all_contracts[:2] if all_contracts else None)
                with f_col4:
                    sort_option = st.selectbox("Sort Order", ["Priority_Score", "Revenue_At_Risk_$", "Churn_Probability_%", "Estimated_CLV_$"], index=0)

                # Sliders
                sl_col1, sl_col2, sl_col3 = st.columns([1, 1, 1])
                with sl_col1:
                    max_t = int(df['Tenure Months'].max()) if 'Tenure Months' in df.columns else 72
                    tenure_range = st.slider("Tenure (Months)", min_value=0, max_value=max_t, value=(0, max_t))
                with sl_col2:
                    max_m = float(df['Monthly Charges'].max()) if 'Monthly Charges' in df.columns else 120.0
                    charges_range = st.slider("Monthly Charges ($)", min_value=0.0, max_value=max_m, value=(0.0, max_m))
                with sl_col3:
                    st.caption("Prioritization Formula:")
                    st.caption("`Priority Score = 60% * P(Churn) + 40% * (CLV / CLV_ref)`")

                # Reconstruct readable columns for presentation if contract is available
                display_df = scored_df.copy()
                if contract_values(df) is not None:
                    display_df['Contract'] = contract_values(df)

                # Filter cohort
                filtered_cohort = filter_customer_cohort(
                    display_df,
                    priority_tiers=filter_tiers if filter_tiers else None,
                    risk_levels=filter_risks if filter_risks else None,
                    contract_types=filter_contracts if filter_contracts else None,
                    min_tenure=tenure_range[0],
                    max_tenure=tenure_range[1],
                    min_monthly_charges=charges_range[0],
                    max_monthly_charges=charges_range[1]
                )

                if not filtered_cohort.empty:
                    # Sort according to selected sort option
                    sorted_cohort = filtered_cohort.sort_values(by=sort_option, ascending=False).reset_index(drop=True)
                    sorted_cohort['Priority_Rank'] = range(1, len(sorted_cohort) + 1)

                    st.markdown(f"**Filtered Cohort Size:** {len(sorted_cohort):,} customers | **Total Revenue at Risk:** ${sorted_cohort['Revenue_At_Risk_$'].sum():,.2f}")

                    # Select columns for clean presentation
                    table_cols = [c for c in ['Priority_Rank', 'Priority_Tier', 'Priority_Score', 'Risk_Level',
                                             'Churn_Probability_%', 'Estimated_CLV_$', 'Revenue_At_Risk_$',
                                             'Recommended_Budget_$', 'Contract', 'Tenure Months', 'Monthly Charges'] if c in sorted_cohort.columns]
                    st.dataframe(sorted_cohort[table_cols].head(100), width="stretch", height=320)

                    csv_dl = sorted_cohort[table_cols].to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="Download Filtered Retention Queue (CSV)",
                        data=csv_dl,
                        file_name="prioritized_retention_cohort.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("No customers match the active filter criteria. Adjust the filters above to expand the cohort.")

            # Retention Campaign Scenario Simulator
            with st.container(border=True):
                st.markdown("### Retention Campaign Scenario Simulator")
                st.caption("Model hypothetical portfolio retention scenarios by tuning intervention cost and effectiveness assumptions.")

                sim_c1, sim_c2, sim_c3, sim_c4 = st.columns(4)
                with sim_c1:
                    sim_reduction = st.slider("Hypothetical Churn Reduction", min_value=5, max_value=50, value=20, step=5, format="%d%%",
                                             help="Assumed relative reduction in churn probability for targeted customers.")
                with sim_c2:
                    sim_cost = st.slider("Cost per Intervention ($)", min_value=5, max_value=100, value=25, step=5,
                                        help="Direct cost per customer targeted (offer discount, outreach, incentive).")
                with sim_c3:
                    sim_budget = st.number_input("Campaign Budget Cap ($)", min_value=500.0, max_value=500000.0, value=15000.0, step=1000.0,
                                                 help="Total allowable retention campaign spend limit.")
                with sim_c4:
                    sim_targets = st.multiselect("Target Priority Cohort", ["Urgent", "High", "Medium", "Low"], default=["Urgent", "High"],
                                                 help="Customer tiers eligible for this campaign.")

                # Run simulation
                sim_result = simulate_retention_campaign(
                    scored_df,
                    assumed_reduction_rate=float(sim_reduction) / 100.0,
                    cost_per_intervention=float(sim_cost),
                    budget_cap=float(sim_budget),
                    target_cohort_column="Priority_Tier",
                    target_cohort_values=sim_targets if sim_targets else ["Urgent", "High"]
                )

                # Display Results
                res1, res2, res3, res4 = st.columns(4)
                res1.metric("Campaign Spend", f"${sim_result['total_campaign_cost_$']:,.2f}", f"{sim_result['targeted_customers']:,} targeted")
                res2.metric("Gross Exposure Saved", f"${sim_result['gross_exposure_reduction_$']:,.2f}", f"Rate: {sim_reduction}%")
                res3.metric("Net Scenario Impact", f"${sim_result['net_scenario_return_$']:,.2f}", "Exposure Saved - Spend")
                res4.metric("Return on Spend Ratio", f"{sim_result['return_on_retention_spend_ratio']:.2f}x", "Gross Saved / Spend")

                if sim_result['remaining_budget_$'] is not None and sim_result['remaining_budget_$'] > 0:
                    st.caption(f"Remaining Unused Budget: **${sim_result['remaining_budget_$']:,.2f}** (Cohort satisfied within budget cap).")

                st.info(f"📌 **Analytical Disclaimer:** {sim_result['disclaimer']}")

        except Exception as sim_err:
            st.error(f"Could not load decision support intelligence: {sim_err}")

elif page == "Predict a customer":
    page_header("CUSTOMER CHECK", "Could this customer leave?",
                "Build a customer profile below. The estimate is based on patterns in the historical dataset.")
    step1, step2, step3 = st.columns(3)
    for col, number, title, detail in [
        (step1, "01", "Account", "Time with company and billing"),
        (step2, "02", "Customer", "Household and services"),
        (step3, "03", "Estimate", "Review the model's result"),
    ]:
        with col, st.container(border=True):
            st.markdown(f"<div class='section-kicker'>{number} / {title.upper()}</div><span class='muted'>{detail}</span>", unsafe_allow_html=True)
    if not ARTIFACT_PATH.is_file():
        st.warning("The prediction tool is not available yet. Train the models first with `python train_model.py`.")
        st.stop()
    try:
        artifact = load_artifact(str(ARTIFACT_PATH), ARTIFACT_PATH.stat().st_mtime)
    except Exception as error:
        st.error(f"Could not load the model artifact: {error}")
        st.stop()
    from src.config import ACTIVE_MODEL_NAME
    model_name = ACTIVE_MODEL_NAME if (ACTIVE_MODEL_NAME != "auto" and ACTIVE_MODEL_NAME in artifact.get("models", {})) else artifact["best_model"]
    model = artifact["models"][model_name]
    feature_columns = artifact["feature_columns"]
    st.caption("Fields with preselected values can be changed to match the customer.")
    values = {}
    with st.form("customer_form"):
        sections = customer_form_sections(feature_columns, df)
        section_names = list(dict.fromkeys(item[0] for item in sections))
        for section in section_names:
            section_items = [item for item in sections if item[0] == section]
            with st.container(border=True):
                st.markdown(f"<div class='section-kicker'>CUSTOMER PROFILE</div>", unsafe_allow_html=True)
                st.markdown(f"### {section}")
                for row_start in range(0, len(section_items), 2):
                    columns = st.columns(2, gap="large")
                    for column, item in zip(columns, section_items[row_start:row_start + 2]):
                        _, kind, label, options = item
                        with column:
                            if kind == "choice":
                                selection = st.selectbox(label, list(options))
                                values.update(options[selection])
                                if label == "Internet service":
                                    values["_internet_service"] = selection
                            elif kind == "single_choice":
                                feature, prompt = label
                                selection = st.selectbox(prompt, list(options))
                                values[feature] = options[selection]
                            elif kind == "number":
                                feature, prompt = label
                                numeric = numeric_series(df, feature).dropna()
                                median = float(numeric.median()) if not numeric.empty else 0.0
                                minimum = float(numeric.min()) if not numeric.empty else 0.0
                                maximum = float(numeric.max()) if not numeric.empty else max(1.0, median)
                                values[feature] = st.number_input(prompt, min_value=minimum, max_value=maximum,
                                    value=min(max(median, minimum), maximum), step=1.0 if pd.api.types.is_integer_dtype(df[feature].dtype) else 0.1)
                            else:
                                feature, prompt = label
                                choices = list(pd.Series(df[feature].dropna().unique()).tolist())
                                values[feature] = st.selectbox(prompt, choices) if choices else np.nan
        if values.get("_internet_service") == "No internet service":
            for feature in feature_columns:
                if feature.endswith("_No internet service"):
                    values[feature] = True
                elif feature.endswith("_Yes") and any(feature.startswith(prefix) for prefix in
                        ["Online Security", "Online Backup", "Device Protection", "Tech Support", "Streaming TV", "Streaming Movies"]):
                    values[feature] = False
        values.pop("_internet_service", None)
        submitted = st.form_submit_button("Check churn likelihood", type="primary", width="stretch")
    if submitted:
        try:
            customer = pd.DataFrame([{col: values[col] for col in feature_columns}], columns=feature_columns)
            active_threshold = artifact.get("threshold", getattr(model, "threshold_", 0.5))
            probabilities = model.predict_proba(customer)[0] if hasattr(model, "predict_proba") else None
            churn_probability = None
            if probabilities is not None:
                class_labels = list(model.classes_)
                if 1 in class_labels:
                    churn_probability = float(probabilities[class_labels.index(1)])
                    prediction = 1 if churn_probability >= active_threshold else 0
                else:
                    prediction = int(model.predict(customer)[0])
            else:
                prediction = int(model.predict(customer)[0])

            if prediction == 1:
                st.markdown("<div class='result-card risk'><div class='section-kicker'>MODEL ESTIMATE</div><h2>This customer may leave</h2><p>The profile shares patterns seen in customers who left the company.</p></div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='result-card stay'><div class='section-kicker'>MODEL ESTIMATE</div><h2>This customer may stay</h2><p>The profile shares patterns seen in customers who continued service.</p></div>", unsafe_allow_html=True)

            if churn_probability is not None:
                risk_level, risk_color = get_risk_tier(churn_probability)
                pred_c1, pred_c2, pred_c3, pred_c4 = st.columns(4)
                pred_c1.metric("Churn Probability", f"{churn_probability:.1%}")
                pred_c2.metric("Retain Probability", f"{(1.0 - churn_probability):.1%}")
                pred_c3.metric("Risk Category", risk_level)
                pred_c4.metric("Active Model", f"{model_name} (Thresh: {active_threshold:.3f})")
                st.progress(churn_probability)

                # Financial impact estimation
                financial_info = calculate_financial_impact(values, churn_probability)
                st.markdown("#### Estimated Financial Exposure")
                fin1, fin2, fin3 = st.columns(3)
                fin1.metric("Customer Lifetime Value (CLV)", f"${financial_info['clv']:,.2f}", f"{financial_info['horizon_months']} mo horizon")
                fin2.metric("Revenue at Risk", f"${financial_info['revenue_at_risk']:,.2f}", "Exposure estimate")
                fin3.metric("Recommended Retention Budget", f"${financial_info['recommended_retention_budget']:,.2f}", "15% policy cap")

                # Principal Feature Drivers
                st.markdown("#### Principal Feature Drivers")
                try:
                    drivers_df = analyze_feature_contributions(model, customer, top_n=6)
                    fig_drv, ax_drv = plt.subplots(figsize=(6.5, 3.2))
                    colors_drv = ["#ef4444" if c > 0 else "#22c55e" for c in drivers_df['Contribution']]
                    ax_drv.barh(drivers_df['Feature'], drivers_df['Contribution'], color=colors_drv, height=0.55)
                    ax_drv.axvline(0, color="#94a3b8", linewidth=1.0)
                    ax_drv.set_xlabel("Relative Contribution to Churn Risk")
                    style_axis(ax_drv, horizontal=True)
                    fig_drv.tight_layout()
                    st.pyplot(fig_drv, width="stretch")
                    plt.close(fig_drv)
                    st.caption("📌 **Analytical Disclaimer:** Feature attributions reflect statistical associations in the trained model and do not indicate causal intervention effects.")
                except Exception as drv_err:
                    st.caption(f"Could not compute individual feature drivers: {drv_err}")

                # Actionable retention recommendations
                st.markdown("#### Actionable Retention Recommendations")
                recs = generate_business_recommendations(values, churn_probability, risk_level)
                for rec in recs:
                    st.markdown(f"- {rec}")

            st.caption("This prediction is an estimate based on historical patterns, not a guaranteed outcome. Individual customer decisions may vary.")
        except Exception as error:
            st.error(f"Could not generate a prediction. Check that all fields contain supported values. Details: {error}")

elif page == "Upload a dataset":
    page_header("BATCH SCORING", "Predict churn for a customer list",
                "Upload a CSV, review a prediction for each row, and download your original data with model results added.")
    if not ARTIFACT_PATH.is_file():
        st.warning("The prediction model has not been trained yet. Run `python train_model.py` first.")
        st.stop()
    try:
        artifact = load_artifact(str(ARTIFACT_PATH), ARTIFACT_PATH.stat().st_mtime)
    except Exception as error:
        st.error(f"Could not load the prediction model: {error}")
        st.stop()

    feature_columns = artifact["feature_columns"]
    template_csv = pd.DataFrame(columns=feature_columns).to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV template", data=template_csv, file_name="customer_input_template.csv",
                       mime="text/csv", help="The template contains the exact customer detail columns this model needs.")
    st.caption("Required details must match the template. Extra columns, such as customer IDs or existing churn labels, are kept in the download but never passed to the model.")
    uploaded_file = st.file_uploader("Choose a customer CSV file", type=["csv"], accept_multiple_files=False)
    if uploaded_file is not None:
        try:
            uploaded_customers = pd.read_csv(uploaded_file)
            if uploaded_customers.empty:
                st.warning("This file has no customer rows to score.")
            else:
                model_inputs = prepare_uploaded_customers(uploaded_customers, feature_columns, df)
                from src.config import ACTIVE_MODEL_NAME
                model_name = ACTIVE_MODEL_NAME if (ACTIVE_MODEL_NAME != "auto" and ACTIVE_MODEL_NAME in artifact.get("models", {})) else artifact["best_model"]
                model = artifact["models"][model_name]
                active_threshold = artifact.get("thresholds", {}).get(model_name, artifact.get("threshold", getattr(model, "threshold_", 0.5)))
                results = uploaded_customers.copy()
                if hasattr(model, "predict_proba"):
                    class_labels = list(model.classes_)
                    if 1 in class_labels:
                        probabilities = model.predict_proba(model_inputs)[:, class_labels.index(1)]
                    else:
                        probabilities = model.predict(model_inputs).astype(float)
                else:
                    probabilities = model.predict(model_inputs).astype(float)

                predictions = (probabilities >= active_threshold).astype(int)
                results['Predicted_Status'] = np.where(predictions == 1, "Churn", "Retain")
                results['Churn_Probability_%'] = np.round(probabilities * 100, 2)
                results['Risk_Level'] = [get_risk_tier(p)[0] for p in probabilities]

                # Financial impact estimation
                raw_tenure = pd.to_numeric(uploaded_customers.get('tenure', uploaded_customers.get('Tenure Months', 12)), errors='coerce').fillna(12.0).clip(lower=0.0)
                raw_monthly = pd.to_numeric(uploaded_customers.get('monthly_charges', uploaded_customers.get('Monthly Charges', 70.0)), errors='coerce').fillna(70.0).clip(lower=0.0)
                expected_months = np.maximum(12.0, 36.0 - np.minimum(raw_tenure, 24.0))
                clvs = np.round(raw_monthly * expected_months, 2)
                at_risks = np.round(clvs * probabilities, 2)
                results['Estimated_CLV_$'] = clvs
                results['Revenue_At_Risk_$'] = at_risks
                results['Recommended_Budget_$'] = np.round(at_risks * 0.15, 2)

                # Retention prioritization
                results = rank_customers(results, preserve_order=False)

                churn_predictions = int((predictions == 1).sum())
                high_risk_count = sum(1 for r in results['Risk_Level'] if r == 'High Risk')
                urgent_count = sum(1 for t in results['Priority_Tier'] if t == 'Urgent')
                total_rev_risk = float(results['Revenue_At_Risk_$'].sum())

                st.success(f"Scored {len(results):,} customer{'s' if len(results) != 1 else ''} successfully using {model_name} (Threshold: {active_threshold:.3f}).")
                k_c1, k_c2, k_c3, k_c4, k_c5 = st.columns(5)
                k_c1.metric("Customers scored", f"{len(results):,}")
                k_c2.metric("Predicted to leave", f"{churn_predictions:,}")
                k_c3.metric("High Risk (>60%)", f"{high_risk_count:,}")
                k_c4.metric("Urgent Priority", f"{urgent_count:,}")
                k_c5.metric("Revenue at Risk", f"${total_rev_risk:,.0f}")

                st.markdown("### Prioritized Customer Results")
                st.dataframe(results, width="stretch", height=420)
                output_csv = results.to_csv(index=False).encode("utf-8")
                st.download_button("Download Prioritized Predictions as CSV", data=output_csv,
                                   file_name="customer_churn_prioritized_results.csv", mime="text/csv",
                                   type="primary")
                st.caption("📌 **Analytical Disclaimer:** Prioritization rankings reflect statistical churn risk and expected revenue exposure. They do not constitute proof of causal intervention effectiveness.")
        except (UnicodeDecodeError, pd.errors.ParserError) as error:
            st.error(f"Could not read this file as a CSV. Please check its format. Details: {error}")
        except ValueError as error:
            st.error(str(error))
        except Exception as error:
            st.error(f"Could not score this file. Check that it follows the template. Details: {error}")

elif page == "Model results":
    page_header("MODEL EVALUATION", "How well do the models perform?",
                "Compare the three trained models using the held-out test customers. Scores describe past test performance, not a guarantee for future customers.")
    if not ARTIFACT_PATH.is_file():
        st.info("No saved evaluation results yet. Run `python train_model.py` to train and compare the three models.")
        st.stop()
    try:
        artifact = load_artifact(str(ARTIFACT_PATH), ARTIFACT_PATH.stat().st_mtime)
    except Exception as error:
        st.error(f"Could not load evaluation results: {error}")
        st.stop()
    metrics = artifact["metrics"]
    table = pd.DataFrame(metrics).T
    st.success(f"Best model by test-set F1-score: {artifact['best_model']}")
    st.caption("Accuracy = all correct predictions. Precision = how often a churn warning was correct. Recall = how many customers who left were identified. F1 balances precision and recall.")

    score_columns = st.columns(3, gap="large")
    friendly_model_names = {
        "Logistic Regression": "Logistic Regression",
        "Decision Tree": "Decision Tree",
        "Random Forest": "Random Forest",
    }
    for column, (name, scores) in zip(score_columns, metrics.items()):
        with column, st.container(border=True):
            st.markdown(f"### {friendly_model_names.get(name, name)}")
            st.metric("F1 score", f"{scores['F1-score']:.3f}")
            st.caption(f"Accuracy {scores['Accuracy']:.3f}  |  Precision {scores['Precision']:.3f}  |  Recall {scores['Recall']:.3f}")

    comparison = table[["Accuracy", "Precision", "Recall", "F1-score", "ROC-AUC"]].rename(columns={
        "Accuracy": "Accuracy", "Precision": "Precision", "Recall": "Recall",
        "F1-score": "F1 score", "ROC-AUC": "ROC-AUC"})
    st.dataframe(comparison.style.format("{:.3f}", na_rep="N/A"), width="stretch")
    selected = st.selectbox("Inspect a model", list(metrics), index=list(metrics).index(artifact["best_model"]))
    metric = metrics[selected]
    left, right = st.columns([1.15, .85], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("### ROC curve comparison")
            st.caption("A curve closer to the upper-left corner separates churn and stay customers better. AUC summarizes the curve; higher is better.")
            curves = artifact.get("roc_curves", {})
            if curves:
                fig, ax = plt.subplots(figsize=(6.5, 4.2))
                colors = {"Logistic Regression": "#087f82", "Decision Tree": "#e3a34b", "Random Forest": "#4668a8"}
                for name, curve in curves.items():
                    auc = metrics[name].get("ROC-AUC")
                    label = f"{name} (AUC {auc:.3f})" if auc is not None else name
                    ax.plot(curve["false_positive_rate"], curve["true_positive_rate"],
                            linewidth=2.2, color=colors.get(name, "#64748b"), label=label)
                ax.plot([0, 1], [0, 1], linestyle="--", color="#9aaaba", linewidth=1)
                ax.set(xlabel="False positive rate", ylabel="True positive rate", xlim=(0, 1), ylim=(0, 1.02))
                ax.legend(frameon=False, loc="lower right", fontsize=8)
                style_axis(ax)
                fig.tight_layout()
                st.pyplot(fig, width="stretch")
                plt.close(fig)
            else:
                st.info("ROC curves are not present in this saved model report. Retrain with `python train_model.py` to create them.")
    with right:
        with st.container(border=True):
            st.markdown(f"### {selected} confusion matrix")
            st.caption("Rows are actual outcomes; columns are model predictions.")
            cm = np.asarray(metric["Confusion matrix"])
            fig, ax = plt.subplots(figsize=(4.5, 4.0))
            sns.heatmap(cm, annot=True, fmt="d", cmap=sns.color_palette(["#f4f8fb", "#087f82"], as_cmap=True),
                        cbar=False, ax=ax, xticklabels=["Stay", "Churn"], yticklabels=["Stay", "Churn"],
                        annot_kws={"size": 13, "weight": "bold"})
            ax.set(xlabel="Predicted", ylabel="Actual")
            fig.tight_layout()
            st.pyplot(fig, width="stretch")
            plt.close(fig)

    with st.container(border=True):
        st.markdown("### Feature importance")
        st.caption("Permutation importance for the selected best model: how much its test-set F1 score changed when one column was shuffled. This indicates association, not cause.")
        if selected == artifact["best_model"]:
            importance = pd.DataFrame(artifact.get("feature_importance", []), columns=["Feature", "Importance"]).head(15)
        else:
            importance = pd.DataFrame()
        if not importance.empty:
            importance = importance.sort_values("Importance")
            fig, ax = plt.subplots(figsize=(9, 5.2))
            ax.barh(importance["Feature"], importance["Importance"], color="#178f8a", height=.68)
            ax.set_xlabel("Change in test F1 score when shuffled")
            style_axis(ax, horizontal=True)
            fig.tight_layout()
            st.pyplot(fig, width="stretch")
            plt.close(fig)
        else:
            st.info(f"Feature importance was saved for {artifact['best_model']}. Select that model to view it.")
    with st.expander("What do the confusion matrix labels mean?"):
        st.write("Rows show what really happened; columns show what the model predicted. A correct prediction is on the diagonal. 'Churn' means the customer left; 'Stay' means they continued service.")
    with st.expander("Technical details for this project"):
        st.write("Detected outcome column:", artifact["target_column"])
        st.write("Columns excluded from training:", ", ".join(artifact["excluded_columns"]) or "None detected")
        st.write("Model input details:", ", ".join(artifact["feature_columns"]))

elif page == "Explore the data":
    page_header("DATA ANALYSIS", "Explore customer patterns",
                "All charts use your processed customer dataset. They describe patterns and do not show what caused a customer to leave.")
    churn_label = y_all.map({0: "Stayed", 1: "Churned"})

    top_left, top_right = st.columns(2, gap="large")
    with top_left:
        with st.container(border=True):
            st.markdown("### Churn distribution")
            count_data = pd.DataFrame({"Outcome": churn_label}).value_counts().rename("Customers").reset_index()
            fig, ax = plt.subplots(figsize=(6, 3.8))
            sns.barplot(data=count_data, x="Outcome", y="Customers", hue="Outcome", legend=False,
                        order=["Stayed", "Churned"], palette={"Stayed": "#168d88", "Churned": "#e3a45b"}, ax=ax)
            ax.set_xlabel("")
            ax.set_ylabel("Number of customers")
            style_axis(ax)
            fig.tight_layout()
            st.pyplot(fig, width="stretch")
            plt.close(fig)
    with top_right:
        with st.container(border=True):
            st.markdown("### Churn by contract type")
            contracts = contract_values(df)
            if contracts is None:
                st.info("A contract field is not available in this dataset.")
            else:
                summary = churn_rate_by_group(contracts, y_all, "Contract")
                fig, ax = plt.subplots(figsize=(6, 3.8))
                bars = ax.barh(summary["Contract"], summary["churn_rate"], color="#168d88", height=.58)
                for bar, rate in zip(bars, summary["churn_rate"]):
                    ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
                            f"{rate:.1f}%", va="center", fontsize=9, color="#344e63")
                ax.set_xlabel("Customers who churned (%)")
                ax.set_xlim(0, max(100, float(summary["churn_rate"].max()) * 1.18))
                style_axis(ax, horizontal=True)
                fig.tight_layout()
                st.pyplot(fig, width="stretch")
                plt.close(fig)

    tenure_column = find_column(df, ["Tenure Months", "Tenure", "tenure"])
    charges_column = find_column(df, ["Monthly Charges", "MonthlyCharges"])
    tenure_panel, charges_panel = st.columns(2, gap="large")
    with tenure_panel:
        with st.container(border=True):
            st.markdown("### Churn by customer tenure")
            if tenure_column:
                summary = churn_rate_by_group(tenure_bands(df, tenure_column), y_all, "Tenure")
                fig, ax = plt.subplots(figsize=(6, 3.8))
                x = np.arange(len(summary))
                ax.plot(x, summary["churn_rate"], marker="o", color="#168d88", linewidth=2.5, markersize=7)
                ax.fill_between(x, summary["churn_rate"].to_numpy(), color="#168d88", alpha=.12)
                ax.set_xticks(x, summary["Tenure"].astype(str))
                ax.set_xlabel("Time with company (months)")
                ax.set_ylabel("Customers who churned (%)")
                ax.set_ylim(bottom=0)
                style_axis(ax)
                fig.tight_layout()
                st.pyplot(fig, width="stretch")
                plt.close(fig)
            else:
                st.info("A tenure field is not available in this dataset.")
    with charges_panel:
        with st.container(border=True):
            st.markdown("### Churn by monthly charges")
            if charges_column:
                charges = numeric_series(df, charges_column)
                valid = charges.notna()
                if charges.loc[valid].nunique() > 1:
                    band_count = min(6, int(charges.loc[valid].nunique()))
                    bands = pd.qcut(charges.loc[valid], q=band_count, duplicates="drop")
                    labels = pd.Series(index=df.index, dtype="object")
                    # Map each customer to a readable charge band while preserving interval order.
                    labels.loc[bands.index] = bands.map(lambda interval: f"${interval.left:.0f}-${interval.right:.0f}").astype(str)
                    summary = churn_rate_by_group(labels, y_all, "Monthly bill")
                    fig, ax = plt.subplots(figsize=(6, 3.8))
                    x = np.arange(len(summary))
                    ax.plot(x, summary["churn_rate"], marker="o", color="#e19a45", linewidth=2.5, markersize=7)
                    ax.fill_between(x, summary["churn_rate"].to_numpy(), color="#e19a45", alpha=.13)
                    ax.set_xticks(x, summary["Monthly bill"].astype(str), rotation=15)
                    ax.set_xlabel("Monthly charges range ($)")
                    ax.set_ylabel("Customers who churned (%)")
                    ax.set_ylim(bottom=0)
                    style_axis(ax)
                    fig.tight_layout()
                    st.pyplot(fig, width="stretch")
                    plt.close(fig)
                else:
                    st.info("Monthly charges need more than one distinct value to compare groups.")
            else:
                st.info("Monthly charges are not available in this dataset.")

    internet = internet_service_values(df)
    paperless_column = next((c for c in df.columns if str(c).strip().lower() == "paperless billing_yes"), None)
    if internet is not None or paperless_column is not None:
        st.markdown("<div class='section-kicker'>ADDITIONAL CUSTOMER SEGMENTS</div>", unsafe_allow_html=True)
        st.subheader("Other useful patterns")
        if internet is not None:
            with st.container(border=True):
                st.markdown("### Churn by internet service")
                summary = churn_rate_by_group(internet, y_all, "Internet service")
                fig, ax = plt.subplots(figsize=(8, 3.5))
                bars = ax.bar(summary["Internet service"], summary["churn_rate"],
                              color=["#168d88", "#42aaa1", "#e3a45b"][:len(summary)], width=.62)
                for bar, rate in zip(bars, summary["churn_rate"]):
                    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                            f"{rate:.1f}%", ha="center", fontsize=9, color="#344e63")
                ax.set_ylabel("Customers who churned (%)")
                ax.set_ylim(0, max(100, float(summary["churn_rate"].max()) * 1.2))
                style_axis(ax)
                fig.tight_layout()
                st.pyplot(fig, width="stretch")
                plt.close(fig)
        if paperless_column is not None:
            with st.container(border=True):
                st.markdown("### Churn by paperless billing")
                labels = flag_values(df[paperless_column]).map({True: "Paperless", False: "Paper bill"})
                summary = churn_rate_by_group(labels, y_all, "Billing")
                fig, ax = plt.subplots(figsize=(8, 3.5))
                bars = ax.bar(summary["Billing"], summary["churn_rate"], color=["#168d88", "#e3a45b"][:len(summary)], width=.62)
                for bar, rate in zip(bars, summary["churn_rate"]):
                    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                            f"{rate:.1f}%", ha="center", fontsize=9, color="#344e63")
                ax.set_ylabel("Customers who churned (%)")
                ax.set_ylim(0, max(100, float(summary["churn_rate"].max()) * 1.2))
                style_axis(ax)
                fig.tight_layout()
                st.pyplot(fig, width="stretch")
                plt.close(fig)

else:
    st.error("Choose a page from the sidebar.")
