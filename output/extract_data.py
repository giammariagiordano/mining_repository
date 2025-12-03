import os
import re
import warnings
import pandas as pd
from radon.complexity import cc_visit

# Fallback per complessità (tollerante a codice "sporco")
try:
    import lizard
    LIZARD_AVAILABLE = True
except ImportError:
    LIZARD_AVAILABLE = False


# ====================================================
# 0. LETTURA CSV
# ====================================================

INPUT_CSV = r"C:\Users\Giammaria\Desktop\output_clean.csv"

df = pd.read_csv(INPUT_CSV)

# Fill di sicurezza
df['author_name'] = df.get('author_name', '').fillna('UNKNOWN')
df['developer_type'] = df.get('developer_type', '').fillna('UNKNOWN')
df['project_name'] = df.get('project_name', '').fillna('UNKNOWN')
df['commit_files'] = df.get('commit_files', '').fillna('')
df['repo_path'] = df.get('repo_path', '').fillna('')


# ====================================================
# 1. PARSING DEI FILE DEL COMMIT (SOLO .py)
# ====================================================

def parse_files(files_str):
    """Trasforma commit_files in lista di file, separando per spazi e virgole."""
    if pd.isna(files_str):
        return []
    parts = re.split(r'[,\s]+', str(files_str).strip())
    return [p for p in parts if p]

df['file_list'] = df['commit_files'].apply(parse_files)

file_df = df[['project_name', 'author_name', 'developer_type', 'commit_sha',
              'file_list']].explode('file_list')

# Consideriamo solo i file Python
file_df = file_df[
    file_df['file_list'].notna()
    & (file_df['file_list'] != '')
    & file_df['file_list'].astype(str).str.endswith('.py')
]

if file_df.empty:
    print("[WARN] Nessun file .py trovato nei commit_files. I CSV di output saranno vuoti o quasi.")

# Identificatore univoco progetto+file
file_df['project_and_file'] = (
    file_df['project_name'].astype(str) + "::" + file_df['file_list'].astype(str)
)


# ====================================================
# 2. OWNERSHIP DEI FILE E FILE TOCCATI PER SVILUPPATORE (solo .py)
# ====================================================

if not file_df.empty:
    file_counts = (
        file_df
        .groupby(['project_name', 'file_list', 'author_name'])
        .size()
        .reset_index(name='touches')
    )

    file_counts['max_for_file'] = file_counts.groupby(
        ['project_name', 'file_list']
    )['touches'].transform('max')

    owners = file_counts[file_counts['touches'] == file_counts['max_for_file']].copy()
    owners['project_and_file'] = (
        owners['project_name'].astype(str) + "::" + owners['file_list'].astype(str)
    )

    owned_files_per_dev = (
        owners
        .groupby('author_name')['project_and_file']
        .apply(list)
        .reset_index(name='owned_files')
    )

    files_touched_per_dev = (
        file_df
        .groupby('author_name')['project_and_file']
        .nunique()
        .reset_index(name='total_files_touched')
    )
else:
    owned_files_per_dev = pd.DataFrame(columns=['author_name', 'owned_files'])
    files_touched_per_dev = pd.DataFrame(columns=['author_name', 'total_files_touched'])


# ====================================================
# 3. PROGETTI E TIPO DI SVILUPPATORE
# ====================================================

projects_per_dev = (
    df.groupby('author_name')['project_name']
    .apply(lambda s: sorted(s.dropna().unique().tolist()))
    .reset_index(name='projects_contributed')
)

# tipo prevalente (SE / ML / Hybrid / altro)
devtype_per_dev = (
    df.groupby('author_name')['developer_type']
    .agg(lambda s: s.value_counts().idxmax() if s.notna().any() else 'UNKNOWN')
    .reset_index(name='developer_type')
)


# ====================================================
# 4. COLONNE A GRANA FINE: SMELLS / ML-SMELLS / VULN / DEADCODE
# ====================================================

impl_cols = [c for c in df.columns if c.startswith('impl_smell_')]
design_cols = [c for c in df.columns if c.startswith('design_smell_')]

ml_cols = [
    c for c in df.columns
    if c.startswith('mlsmell_')
    and c not in ['mlsmell_total', 'mlsmell_files', 'mlsmell_details']
]

vuln_cols = [
    c for c in df.columns
    if c.startswith('vuln_bandit_')
    and not c.endswith('_summaries')
    and not c.endswith('_details')
]

deadcode_cols = [
    c for c in df.columns
    if c.startswith('deadcode_')
    and not c.endswith('_summaries')
    and not c.endswith('_details')
]

fine_cols = impl_cols + design_cols + ml_cols + vuln_cols + deadcode_cols


# ====================================================
# 5. AGGREGAZIONE PER SVILUPPATORE: CARRIERA INTERA
# ====================================================

agg_dict = {col: 'sum' for col in fine_cols}

if 'fix_commit' in df.columns:
    agg_dict['fix_commit'] = 'sum'
if 'szz_introducing_commits_count' in df.columns:
    agg_dict['szz_introducing_commits_count'] = 'sum'

career = df.groupby('author_name').agg(agg_dict).reset_index()

commits_per_dev = (
    df.groupby('author_name')
    .size()
    .reset_index(name='total_commits')
)

career = career.merge(commits_per_dev, on='author_name', how='left')
career = career.merge(devtype_per_dev, on='author_name', how='left')
career = career.merge(projects_per_dev, on='author_name', how='left')
career = career.merge(files_touched_per_dev, on='author_name', how='left')
career = career.merge(owned_files_per_dev, on='author_name', how='left')

career['owned_files'] = career['owned_files'].apply(
    lambda x: x if isinstance(x, list) else []
)

if 'fix_commit' in career.columns:
    career['bugs_fixed'] = career['fix_commit']
else:
    career['bugs_fixed'] = 0

if 'szz_introducing_commits_count' in career.columns:
    career['bugs_introduced'] = career['szz_introducing_commits_count']
    career['bug_introducing_ratio'] = (
        career['bugs_introduced'] /
        career['total_commits'].replace({0: pd.NA})
    )
else:
    career['bugs_introduced'] = 0
    career['bug_introducing_ratio'] = pd.NA

# One-hot per tipo sviluppatore
career['is_se_engineer'] = (career['developer_type'] == 'SE-engineer').astype(int)
career['is_ml_engineer'] = (career['developer_type'] == 'ML-engineer').astype(int)
career['is_hybrid_engineer'] = (career['developer_type'] == 'Hybrid-engineer').astype(int)

meta_cols = [
    'author_name',
    'developer_type',
    'is_se_engineer',
    'is_ml_engineer',
    'is_hybrid_engineer',
    'total_commits',
    'projects_contributed',
    'total_files_touched',    # file .py
    'owned_files',            # file .py di cui è owner
    'bugs_introduced',
    'bugs_fixed',
    'bug_introducing_ratio',
]

other_cols = [c for c in career.columns if c not in meta_cols]
ordered_cols = meta_cols + sorted(other_cols)
career = career[ordered_cols]


# ====================================================
# 6. ANALISI A LIVELLO DI FILE (SOLO .py)
# ====================================================

if not file_df.empty:
    # ---- 6.1 Lista persone che hanno toccato il file ----
    touched_by = (
        file_df.groupby('project_and_file')['author_name']
        .apply(lambda x: sorted(x.unique().tolist()))
        .reset_index(name='touched_by')
    )

    # ---- 6.2 Percentuali e liste SE / ML / Hybrid-engineer per file ----
    def type_ratio(group):
        """
        Per un dato file:
          - considera solo developer_type in {SE-engineer, ML-engineer, Hybrid-engineer}
          - pct_xxx = #XXX / (#SE + #ML + #Hybrid)
          - restituisce anche le liste di nomi per categoria.
        """
        types = group[['author_name', 'developer_type']].drop_duplicates()
        valid_types = ['SE-engineer', 'ML-engineer', 'Hybrid-engineer']
        types = types[types['developer_type'].isin(valid_types)]

        total = len(types)
        se_devs = sorted(
            types.loc[types['developer_type'] == 'SE-engineer', 'author_name'].tolist()
        )
        ml_devs = sorted(
            types.loc[types['developer_type'] == 'ML-engineer', 'author_name'].tolist()
        )
        hy_devs = sorted(
            types.loc[types['developer_type'] == 'Hybrid-engineer', 'author_name'].tolist()
        )

        se = len(se_devs)
        ml = len(ml_devs)
        hy = len(hy_devs)

        denom = se + ml + hy

        if denom == 0:
            return pd.Series({
                'pct_se_engineer': 0.0,
                'pct_ml_engineer': 0.0,
                'pct_hybrid_engineer': 0.0,
                'num_se_engineer': 0,
                'num_ml_engineer': 0,
                'num_hybrid_engineer': 0,
                'se_engineers': [],
                'ml_engineers': [],
                'hybrid_engineers': [],
            })

        return pd.Series({
            'pct_se_engineer': se / denom,
            'pct_ml_engineer': ml / denom,
            'pct_hybrid_engineer': hy / denom,
            'num_se_engineer': se,
            'num_ml_engineer': ml,
            'num_hybrid_engineer': hy,
            'se_engineers': se_devs,
            'ml_engineers': ml_devs,
            'hybrid_engineers': hy_devs,
        })

    type_stats = file_df.groupby('project_and_file').apply(type_ratio).reset_index()
else:
    touched_by = pd.DataFrame(columns=['project_and_file', 'touched_by'])
    type_stats = pd.DataFrame(columns=[
        'project_and_file',
        'pct_se_engineer', 'pct_ml_engineer', 'pct_hybrid_engineer',
        'num_se_engineer', 'num_ml_engineer', 'num_hybrid_engineer',
        'se_engineers', 'ml_engineers', 'hybrid_engineers'
    ])


# ---- 6.3 Complessità ciclomatica reale + LOC reali per file .py ----
project_repos = (
    df[['project_name', 'repo_path']]
    .dropna()
    .drop_duplicates()
)

complexity_loc_records = []

for _, row in project_repos.iterrows():
    project = row['project_name']
    repo_root = row['repo_path']
    if not repo_root:
        continue

    repo_root = os.path.abspath(repo_root)
    if not os.path.isdir(repo_root):
        print(f"[WARN] repo_path non esistente: {repo_root}")
        continue

    print(f"[INFO] Analizzo repo per complessità/LOC: {project} -> {repo_root}")

    for root, _, files in os.walk(repo_root):
        for name in files:
            if not name.endswith('.py'):
                continue

            abs_path = os.path.join(root, name)
            rel_path = os.path.relpath(abs_path, repo_root).replace("\\", "/")

            # --- Lettura codice e LOC ---
            try:
                with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                    code = f.read()
            except Exception as e:
                print(f"[WARN] lettura file fallita per {abs_path}: {e}")
                continue

            loc = code.count('\n') + 1 if code else 0

            cc_avg = None
            cc_max = None
            complexity_tool = None    # "radon", "lizard", "unparsed_py2", "unparsed_unknown"
            py2_suspected = False

            # --- Step 1: radon sul codice originale ---
            blocks = []
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=SyntaxWarning)
                try:
                    blocks = cc_visit(code)
                    if blocks:
                        complexity_tool = "radon"
                except SyntaxError as e:
                    py2_suspected = True
                    print(f"[INFO] possibile Python 2 o sintassi non valida per {abs_path}: {e}")
                except Exception as e:
                    print(f"[WARN] cc_visit fallito per {abs_path}: {e}")

            # --- Step 2: fallback su lizard (se radon fallisce) ---
            if (not blocks) and LIZARD_AVAILABLE:
                try:
                    liz_result = lizard.analyze_file(abs_path)
                    funs = liz_result.function_list
                    if funs:
                        ccs = [f.cyclomatic_complexity for f in funs]
                        cc_avg = sum(ccs) / len(ccs)
                        cc_max = max(ccs)
                        complexity_tool = "lizard"
                    else:
                        cc_avg = 0.0
                        cc_max = 0.0
                        complexity_tool = "lizard"
                except Exception as e:
                    print(f"[WARN] lizard fallito per {abs_path}: {e}")

            # --- Se abbiamo blocchi radon, usiamo quelli ---
            if blocks:
                complexities = [b.complexity for b in blocks]
                cc_avg = sum(complexities) / len(complexities)
                cc_max = max(complexities)

            # --- Se ancora non abbiamo complessità, mettiamo flag ---
            if cc_avg is None or cc_max is None:
                if py2_suspected:
                    complexity_tool = "unparsed_py2"
                else:
                    complexity_tool = "unparsed_unknown"

            complexity_loc_records.append({
                'project_name': project,
                'file_path': rel_path,
                'loc': loc,
                'cc_avg': cc_avg,
                'cc_max': cc_max,
                'py2_suspected': py2_suspected,
                'complexity_tool': complexity_tool,
            })

size_complexity_agg = pd.DataFrame(complexity_loc_records)
if not size_complexity_agg.empty:
    size_complexity_agg['project_and_file'] = (
        size_complexity_agg['project_name'] + "::" + size_complexity_agg['file_path']
    )
else:
    size_complexity_agg = pd.DataFrame(
        columns=[
            'project_and_file', 'project_name', 'file_path',
            'loc', 'cc_avg', 'cc_max', 'py2_suspected', 'complexity_tool'
        ]
    )


# ---- 6.4 Bug per file, propagando SZZ e fix_commit ai file .py ----
bug_agg = None
bug_fix_agg = None

if "szz_introducing_commits_count" in df.columns:
    szz_df = df[['project_name', 'commit_sha', 'file_list',
                 'szz_introducing_commits_count']].explode('file_list')

    szz_df = szz_df[
        szz_df['file_list'].notna()
        & (szz_df['file_list'] != '')
        & szz_df['file_list'].astype(str).str.endswith('.py')
    ]

    szz_df['project_and_file'] = (
        szz_df['project_name'].astype(str) + "::" + szz_df['file_list'].astype(str)
    )

    bug_agg = (
        szz_df
        .groupby('project_and_file')['szz_introducing_commits_count']
        .sum()
        .reset_index(name='bugs_introduced')
    )

if "fix_commit" in df.columns:
    fix_df = df[['project_name', 'commit_sha', 'file_list', 'fix_commit']].explode('file_list')

    fix_df = fix_df[
        fix_df['file_list'].notna()
        & (fix_df['file_list'] != '')
        & fix_df['file_list'].astype(str).str.endswith('.py')
    ]

    fix_df['project_and_file'] = (
        fix_df['project_name'].astype(str) + "::" + fix_df['file_list'].astype(str)
    )

    bug_fix_agg = (
        fix_df
        .groupby('project_and_file')['fix_commit']
        .sum()
        .reset_index(name='bugfix_commits_touching_file')
    )


# ---- 6.5 SMELLS / VULN / DEADCODE A LIVELLO DI FILE (SOLO .py) ----
if fine_cols:
    smell_file_df = df[['project_name', 'file_list'] + fine_cols].explode('file_list')
    smell_file_df = smell_file_df[
        smell_file_df['file_list'].notna()
        & (smell_file_df['file_list'] != '')
        & smell_file_df['file_list'].astype(str).str.endswith('.py')
    ]
    smell_file_df['project_and_file'] = (
        smell_file_df['project_name'].astype(str) + "::" + smell_file_df['file_list'].astype(str)
    )

    smell_file_agg = (
        smell_file_df
        .groupby('project_and_file')[fine_cols]
        .sum()
        .reset_index()
    )
else:
    smell_file_agg = pd.DataFrame(columns=['project_and_file'])


# ---- 6.6 Join finale per file-level ----
file_level = touched_by.merge(type_stats, on='project_and_file', how='left')
file_level = file_level.merge(size_complexity_agg, on='project_and_file', how='left')

if bug_agg is not None:
    file_level = file_level.merge(bug_agg, on='project_and_file', how='left')
else:
    file_level['bugs_introduced'] = pd.NA

if bug_fix_agg is not None:
    file_level = file_level.merge(bug_fix_agg, on='project_and_file', how='left')
else:
    file_level['bugfix_commits_touching_file'] = pd.NA

if not smell_file_agg.empty:
    file_level = file_level.merge(smell_file_agg, on='project_and_file', how='left')

# Riempiamo NaN in percentuali e conteggi
file_level['pct_se_engineer'] = file_level['pct_se_engineer'].fillna(0.0)
file_level['pct_ml_engineer'] = file_level['pct_ml_engineer'].fillna(0.0)
file_level['pct_hybrid_engineer'] = file_level['pct_hybrid_engineer'].fillna(0.0)

file_level['num_se_engineer'] = file_level['num_se_engineer'].fillna(0).astype(int)
file_level['num_ml_engineer'] = file_level['num_ml_engineer'].fillna(0).astype(int)
file_level['num_hybrid_engineer'] = file_level['num_hybrid_engineer'].fillna(0).astype(int)

# Se le liste per categoria sono NaN, sostituiamo con liste vuote
for col in ['se_engineers', 'ml_engineers', 'hybrid_engineers']:
    if col in file_level.columns:
        file_level[col] = file_level[col].apply(
            lambda x: x if isinstance(x, list) else []
        )

# Per i singoli smell / vuln / deadcode, se presenti, riempiamo con 0
for col in fine_cols:
    if col in file_level.columns:
        file_level[col] = file_level[col].fillna(0)

# Splitta project_and_file in due colonne leggibili
proj_file_split = file_level['project_and_file'].str.split("::", n=1, expand=True)
file_level['project_name_csv'] = proj_file_split[0]
file_level['file_path_csv'] = proj_file_split[1]

# Ordina le colonne del file-level (smell/vuln/deadcode restano in coda)
file_meta_cols = [
    'project_name_csv',
    'file_path_csv',
    'project_and_file',
    'touched_by',
    'se_engineers',
    'ml_engineers',
    'hybrid_engineers',
    'num_se_engineer',
    'num_ml_engineer',
    'num_hybrid_engineer',
    'pct_se_engineer',
    'pct_ml_engineer',
    'pct_hybrid_engineer',
    'loc',
    'cc_avg',
    'cc_max',
    'py2_suspected',
    'complexity_tool',
    'bugs_introduced',
    'bugfix_commits_touching_file'
]

other_file_cols = [c for c in file_level.columns if c not in file_meta_cols]
file_level = file_level[file_meta_cols + sorted(other_file_cols)]


# ====================================================
# 7. SALVATAGGIO OUTPUT
# ====================================================

career_output = "developer_career_summary.csv"
file_output = "file_level_metrics.csv"
clean_file_output = "file_level_metrics_clean.csv"

career.to_csv(career_output, index=False)
file_level.to_csv(file_output, index=False)

print(f"Creato: {career_output}")
print(career.head())
print()
print(f"Creato: {file_output}")
print(file_level.head())

# ====================================================
# 8. CSV PULITO: NIENTE NaN, loc>0, complessità>0
# ====================================================

file_level_clean = file_level.copy()

# Scarta righe con loc <= 0 o cc_max <= 0
file_level_clean = file_level_clean[
    (file_level_clean['loc'] > 0) &
    (file_level_clean['cc_max'].notna()) &
    (file_level_clean['cc_max'] > 0)
]

# Riempi eventuali NaN residui:
num_cols = file_level_clean.select_dtypes(include=['number']).columns
obj_cols = file_level_clean.select_dtypes(include=['object']).columns

file_level_clean[num_cols] = file_level_clean[num_cols].fillna(0)
file_level_clean[obj_cols] = file_level_clean[obj_cols].fillna('')

file_level_clean.to_csv(clean_file_output, index=False)

print()
print(f"Creato CSV pulito (no NaN, loc>0, cc_max>0): {clean_file_output}")
print(file_level_clean.head())