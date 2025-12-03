import os
import pandas as pd
import numpy as np
from scipy.stats import kruskal, mannwhitneyu
import matplotlib.pyplot as plt

# =============================================================================
# CONFIGURATION
# =============================================================================

# Path to your CSV file (change this to your real path)
CSV_PATH = r"C:\Users\Giammaria\Desktop\mining_repository\output\file_level_metrics_clean.csv"

# Directory for plots (one subfolder per stratum)
PLOTS_DIR_BASE = "analysis_plots_strata"

# Output CSV with pairwise summary (p-values + stars + Cliff's delta) for all strata
SUMMARY_TABLE_PATH = "pairwise_summary_strata.csv"

GROUP_COL = "group"
GROUPS = ["SE", "ML", "Hybrid"]

# CONTROL_VARS will be set in main() (loc, cc_avg, ratio_control)
CONTROL_VARS = []


# =============================================================================
# HELPERS
# =============================================================================

def count_list(x):
    """
    If the column num_* stores strings like "['a','b']",
    return the number of elements. If it is already numeric, return as is.
    """
    if isinstance(x, str):
        s = x.strip().strip("[]")
        if s.strip() == "":
            return 0
        return len([item for item in s.split(",")])
    return x


def classify_group(row):
    """
    Classify files into:
      - SE: only SE engineers
      - ML: only ML engineers
      - Hybrid: everything else (any combination or at least one hybrid engineer)
    """
    se = row["num_se_engineer"] > 0
    ml = row["num_ml_engineer"] > 0
    hy = row["num_hybrid_engineer"] > 0

    if se and not ml and not hy:
        return "SE"
    if ml and not se and not hy:
        return "ML"
    if (se and ml) or hy or (se and hy) or (ml and hy):
        return "Hybrid"
    return "Other"


def residualize(y, X):
    """
    Perform linear regression y ~ X and return residuals.
    y: array (n,)
    X: array (n, k) with the first column = 1 for the intercept.
    Returns:
      resid (array), mask (boolean array of rows used)
    """
    mask = ~np.isnan(y) & ~np.any(np.isnan(X), axis=1)
    y_valid = y[mask]
    X_valid = X[mask]

    if len(y_valid) == 0:
        raise ValueError("No valid data left after removing NaNs for residualization")

    beta, *_ = np.linalg.lstsq(X_valid, y_valid, rcond=None)
    y_hat = X_valid @ beta
    resid = y_valid - y_hat
    return resid, mask


def cliffs_delta(x, y):
    """
    Compute Cliff's delta for two arrays x, y.
    Returns a value in [-1, 1].
    Positive -> x tends to have larger values than y.
    """
    x = list(x)
    y = list(y)
    n = len(x)
    m = len(y)
    gt = 0
    lt = 0
    for xi in x:
        for yj in y:
            if xi > yj:
                gt += 1
            elif xi < yj:
                lt += 1
    delta = (gt - lt) / (n * m)
    return delta


def p_to_stars(p):
    """
    Map p-value to significance stars:
      p < 0.001 -> '***'
      p < 0.01  -> '**'
      p < 0.05  -> '*'
      else      -> ''
    """
    if p < 0.001:
        return "***"
    elif p < 0.01:
        return "**"
    elif p < 0.05:
        return "*"
    else:
        return ""


def kruskal_with_posthoc(df, outcome_col, group_col=GROUP_COL, controls=None):
    """
    1) Residualize outcome with respect to covariates in `controls`
    2) Run Kruskal–Wallis on residuals (if non-constant, and at least 2 groups with data)
    3) Run pairwise Mann–Whitney U (SE-ML, SE-Hybrid, ML-Hybrid) with Bonferroni
       ONLY for pairs where both groups have data.
    4) Compute Cliff's delta on residuals for each pair.
    """
    if controls is None:
        raise ValueError("controls must be provided")

    # outcome
    y = pd.to_numeric(df[outcome_col], errors="coerce").values

    # X = [1, controls...]
    X = np.column_stack([
        np.ones(len(df)),
        *[pd.to_numeric(df[c], errors="coerce").values for c in controls]
    ])

    resid, mask = residualize(y, X)
    df_valid = df.iloc[np.where(mask)[0]].copy()
    resid_col = f"{outcome_col}_resid"
    df_valid[resid_col] = resid

    # data by group
    data_by_group = {}
    for g in GROUPS:
        vals = df_valid[df_valid[group_col] == g][resid_col].values
        data_by_group[g] = vals

    # Consider only groups that actually have data
    present_groups = [g for g, vals in data_by_group.items() if len(vals) > 0]

    # If fewer than 2 groups have data, no test is possible
    if len(present_groups) < 2:
        pairwise = {}
        for pair in [("SE", "ML"), ("SE", "Hybrid"), ("ML", "Hybrid")]:
            pairwise[pair] = {
                "U": np.nan,
                "p_raw": np.nan,
                "p_adj": np.nan,
                "stars": "",
                "delta": np.nan,
            }
        return {
            "outcome": outcome_col,
            "kw_stat": np.nan,
            "kw_p": np.nan,
            "pairwise": pairwise,
            "df_valid": df_valid,
            "resid_col": resid_col,
        }

    # Check if all residuals in all present groups are identical
    all_vals = np.concatenate([data_by_group[g] for g in present_groups])
    if np.allclose(all_vals, all_vals[0]):
        pairwise = {}
        for pair in [("SE", "ML"), ("SE", "Hybrid"), ("ML", "Hybrid")]:
            pairwise[pair] = {
                "U": np.nan,
                "p_raw": np.nan,
                "p_adj": np.nan,
                "stars": "",
                "delta": np.nan,
            }
        return {
            "outcome": outcome_col,
            "kw_stat": np.nan,
            "kw_p": np.nan,
            "pairwise": pairwise,
            "df_valid": df_valid,
            "resid_col": resid_col,
        }

    # Kruskal–Wallis on present groups only
    kw_stat, kw_p = kruskal(*(data_by_group[g] for g in present_groups))

    # Pairwise Mann–Whitney U with Bonferroni + Cliff's delta
    pairs = [("SE", "ML"), ("SE", "Hybrid"), ("ML", "Hybrid")]
    pairwise = {}
    raw_ps = []

    for g1, g2 in pairs:
        v1 = data_by_group[g1]
        v2 = data_by_group[g2]

        # If one of the groups has no data in this stratum, skip (NaN)
        if len(v1) == 0 or len(v2) == 0:
            U, p, delta = np.nan, np.nan, np.nan
        else:
            U, p = mannwhitneyu(v1, v2, alternative="two-sided")
            delta = cliffs_delta(v1, v2)

        pairwise[(g1, g2)] = {"U": U, "p_raw": p, "delta": delta}
        raw_ps.append(p)

    # Bonferroni correction
    m = len(pairs)
    adj_ps = []
    for p in raw_ps:
        if p == p:  # not NaN
            adj_ps.append(min(p * m, 1.0))
        else:
            adj_ps.append(np.nan)

    for (pair, vals), p_adj in zip(pairwise.items(), adj_ps):
        vals["p_adj"] = p_adj
        vals["stars"] = p_to_stars(p_adj) if p_adj == p_adj else ""

    return {
        "outcome": outcome_col,
        "kw_stat": kw_stat,
        "kw_p": kw_p,
        "pairwise": pairwise,
        "df_valid": df_valid,
        "resid_col": resid_col,
    }


def make_plots(df_valid, outcome_label, outcome_col, resid_col, plots_dir):
    """
    Create and save:
      - Boxplot (raw values by group)
      - Boxplot (residuals by group)
      - Violin plot (residuals by group)
      - Barplot of raw means by group

    Robust to cases where some groups have no data in a given stratum.
    """
    os.makedirs(plots_dir, exist_ok=True)

    raw_data = []
    resid_data = []
    means = []
    group_labels = []

    for g in GROUPS:
        sub = df_valid[df_valid[GROUP_COL] == g]
        raw_vals = pd.to_numeric(sub[outcome_col], errors="coerce").values
        resid_vals = pd.to_numeric(sub[resid_col], errors="coerce").values

        # Skip groups with no data
        if len(raw_vals) == 0 or len(resid_vals) == 0:
            continue

        raw_data.append(raw_vals)
        resid_data.append(resid_vals)
        means.append(np.nanmean(raw_vals))
        group_labels.append(g)

    # If we have fewer than 2 groups with data, plotting is not very meaningful
    if len(group_labels) < 2:
        return

    # ----- BOX PLOT (raw values) -----
    plt.figure()
    plt.boxplot(raw_data, tick_labels=group_labels)
    plt.title(f"Boxplot (raw values) - {outcome_label}")
    plt.xlabel("Group")
    plt.ylabel(outcome_label)
    plt.tight_layout()
    out_path = os.path.join(plots_dir, f"{outcome_label}_boxplot_raw.png")
    plt.savefig(out_path, dpi=300)
    plt.close()

    # ----- BOX PLOT (residuals) -----
    plt.figure()
    plt.boxplot(resid_data, tick_labels=group_labels)
    plt.title(f"Boxplot (residuals) - {outcome_label}")
    plt.xlabel("Group")
    plt.ylabel(f"{outcome_label} residuals")
    plt.tight_layout()
    out_path = os.path.join(plots_dir, f"{outcome_label}_boxplot_resid.png")
    plt.savefig(out_path, dpi=300)
    plt.close()

    # ----- VIOLIN PLOT (residuals) -----
    plt.figure()
    plt.violinplot(resid_data, showmeans=True, showmedians=True)
    plt.xticks(range(1, len(group_labels) + 1), group_labels)
    plt.title(f"Violin plot (residuals) - {outcome_label}")
    plt.xlabel("Group")
    plt.ylabel(f"{outcome_label} residuals")
    plt.tight_layout()
    out_path = os.path.join(plots_dir, f"{outcome_label}_violin_resid.png")
    plt.savefig(out_path, dpi=300)
    plt.close()

    # ----- BARPLOT of raw means -----
    x = np.arange(len(group_labels)) + 1
    plt.figure()
    plt.bar(x, means)
    plt.xticks(x, group_labels)
    plt.title(f"Raw means - {outcome_label}")
    plt.xlabel("Group")
    plt.ylabel(f"Mean {outcome_label}")
    plt.tight_layout()
    out_path = os.path.join(plots_dir, f"{outcome_label}_bar_means_raw.png")
    plt.savefig(out_path, dpi=300)
    plt.close()


def stratify_ratio(df):
    """
    Stratify files into LOW, MID, HIGH strata based on ratio_control:
    - LOW = bottom 33%
    - MID = 33% to 66%
    - HIGH = top 33%
    """
    q33 = df["ratio_control"].quantile(0.33)
    q66 = df["ratio_control"].quantile(0.66)

    def assign_stratum(x):
        if x <= q33:
            return "LOW"
        elif x <= q66:
            return "MID"
        else:
            return "HIGH"

    df["ratio_stratum"] = df["ratio_control"].apply(assign_stratum)
    return df


# =============================================================================
# MAIN
# =============================================================================

def main():
    # Summary for all strata
    all_summary_rows = []

    # --- Load data ---
    df = pd.read_csv(CSV_PATH)

    # Normalize num_* if they are list-like strings
    for col in ["num_se_engineer", "num_ml_engineer", "num_hybrid_engineer"]:
        if col in df.columns:
            df[col] = df[col].apply(count_list)
        else:
            raise KeyError(f"Missing column {col} in CSV")

    # Group classification
    df[GROUP_COL] = df.apply(classify_group, axis=1)
    df = df[df[GROUP_COL].isin(GROUPS)].copy()

    # Control covariates (basic)
    for c in ["loc", "cc_avg"]:
        if c not in df.columns:
            raise KeyError(f"Missing control variable {c} in CSV")
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["loc", "cc_avg"])

    # Add SE/ML ratio control
    df["ratio_se_ml_raw"] = df["num_se_engineer"] / df["num_ml_engineer"].replace(0, 1)
    df["ratio_control"] = np.log1p(df["ratio_se_ml_raw"])

    global CONTROL_VARS
    CONTROL_VARS = ["loc", "cc_avg", "ratio_control"]

    # Build aggregated (coarse) outcomes
    design_cols = [c for c in df.columns if c.startswith("design_smell_")]
    impl_cols = [c for c in df.columns if c.startswith("impl_smell_")]
    df["generic_code_smells_total"] = df[design_cols + impl_cols].sum(axis=1)

    ml_cols = [c for c in df.columns if c.startswith("mlsmell_")]
    df["ml_smells_total"] = df[ml_cols].sum(axis=1)

    coarse_outcomes = {
        "bugs_introduced": "bugs_introduced",
        "vulnerabilities": "vuln_bandit_issues_total",
        "generic_code_smells_total": "generic_code_smells_total",
        "ml_smells_total": "ml_smells_total",
        "deadcode_items_total": "deadcode_items_total",
    }

    vuln_fine = [
        c for c in df.columns
        if c.startswith("vuln_bandit_issues_") and c != "vuln_bandit_issues_total"
    ]
    deadcode_fine = [
        c for c in df.columns
        if c.startswith("deadcode_items_") and c != "deadcode_items_total"
    ]
    design_fine = design_cols[:]
    impl_fine = impl_cols[:]
    ml_fine = ml_cols[:]

    fine_outcomes = vuln_fine + deadcode_fine + design_fine + impl_fine + ml_fine

    # Stratify
    df = stratify_ratio(df)
    strata = ["LOW", "MID", "HIGH"]

    # Ensure base plot directory
    os.makedirs(PLOTS_DIR_BASE, exist_ok=True)

    # STRATIFIED ANALYSIS
    for STRAT in strata:
        df_s = df[df["ratio_stratum"] == STRAT].copy()

        text_out = f"analysis_results_{STRAT}.txt"
        plots_dir = os.path.join(PLOTS_DIR_BASE, STRAT)
        os.makedirs(plots_dir, exist_ok=True)

        with open(text_out, "w", encoding="utf-8") as fout:
            fout.write(f"=== STRATIFIED ANALYSIS: {STRAT} ===\n")
            fout.write(f"Files in stratum: {len(df_s)}\n\n")

            # Coarse outcomes
            fout.write("==== COARSE-GRANULARITY OUTCOMES ====\n\n")

            for label, col in coarse_outcomes.items():

                fout.write("=" * 80 + "\n")
                fout.write(f"[{STRAT} - COARSE] Outcome: {label} (col: {col})\n")
                fout.write("=" * 80 + "\n")

                res = kruskal_with_posthoc(df_s, outcome_col=col, controls=CONTROL_VARS)
                kw_stat = res["kw_stat"]
                kw_p = res["kw_p"]
                df_valid = res["df_valid"]
                resid_col = res["resid_col"]

                fout.write(f"Kruskal–Wallis H = {kw_stat}, p = {kw_p}\n\n")

                fout.write("Raw summaries:\n")
                for g in GROUPS:
                    sub = df_s[df_s[GROUP_COL] == g]
                    fout.write(
                        f"  {g:<6} n={len(sub):<5d}"
                        f" mean={sub[col].mean():.3f}"
                        f" median={sub[col].median():.3f}\n"
                    )
                fout.write("\n")

                fout.write("Post-hoc (Bonferroni) + Cliff's delta:\n")
                for (g1, g2), vals in res["pairwise"].items():
                    U = vals["U"]
                    p_raw = vals["p_raw"]
                    p_adj = vals["p_adj"]
                    delta = vals["delta"]
                    stars = vals["stars"]

                    fout.write(
                        f"  {g1} vs {g2}: U={U}, p_raw={p_raw}, "
                        f"p_adj={p_adj} {stars}, delta={delta}\n"
                    )

                    all_summary_rows.append({
                        "stratum": STRAT,
                        "granularity": "coarse",
                        "outcome": label,
                        "column": col,
                        "comparison": f"{g1} vs {g2}",
                        "U": U,
                        "p_raw": p_raw,
                        "p_adj": p_adj,
                        "significance": stars,
                        "cliffs_delta": delta,
                    })

                fout.write("\n")

                make_plots(df_valid, label, col, resid_col, plots_dir)

            # Fine outcomes
            fout.write("==== FINE-GRANULARITY OUTCOMES ====\n\n")

            for col in fine_outcomes:
                label = col

                fout.write("=" * 80 + "\n")
                fout.write(f"[{STRAT} - FINE] {label}\n")
                fout.write("=" * 80 + "\n")

                res = kruskal_with_posthoc(df_s, outcome_col=col, controls=CONTROL_VARS)
                kw_stat = res["kw_stat"]
                kw_p = res["kw_p"]
                df_valid = res["df_valid"]
                resid_col = res["resid_col"]

                fout.write(f"Kruskal–Wallis H = {kw_stat}, p = {kw_p}\n\n")

                fout.write("Raw summaries:\n")
                for g in GROUPS:
                    sub = df_s[df_s[GROUP_COL] == g]
                    fout.write(
                        f"  {g:<6} n={len(sub):<5d}"
                        f" mean={sub[col].mean():.3f}"
                        f" median={sub[col].median():.3f}\n"
                    )
                fout.write("\n")

                fout.write("Post-hoc (Bonferroni) + Cliff's delta:\n")
                for (g1, g2), vals in res["pairwise"].items():
                    U = vals["U"]
                    p_raw = vals["p_raw"]
                    p_adj = vals["p_adj"]
                    delta = vals["delta"]
                    stars = vals["stars"]

                    fout.write(
                        f"  {g1} vs {g2}: U={U}, p_raw={p_raw}, "
                        f"p_adj={p_adj} {stars}, delta={delta}\n"
                    )

                    all_summary_rows.append({
                        "stratum": STRAT,
                        "granularity": "fine",
                        "outcome": label,
                        "column": col,
                        "comparison": f"{g1} vs {g2}",
                        "U": U,
                        "p_raw": p_raw,
                        "p_adj": p_adj,
                        "significance": stars,
                        "cliffs_delta": delta,
                    })

                fout.write("\n")

    # Save summary table
    summary_df = pd.DataFrame(all_summary_rows)
    summary_df.to_csv(SUMMARY_TABLE_PATH, index=False)
    print(f"Saved stratified summary to {SUMMARY_TABLE_PATH}")


if __name__ == "__main__":
    main()