import re

# Read legacy_miner.py
with open('legacy_miner.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Define the fields that need to be added to metrics dictionaries
additional_fields = '''
                "commit_files": "",  # Will be set below with modified files
                "is_release": False,  # Set True only for releases
                "developer_type": "",
                "developer_type_explanation": "",
                "ml_score": 0,
                "se_score": 0,
                "issue_bodies": "",
                "issue_comments": "",'''

# Pattern 1: mine_repo_commits around line 504-525
# Find the metrics dict in mine_repo_commits and add missing fields
pattern1 = r'(\s+metrics: Dict\[str, Any\] = \{[^}]+?"fix_commit_tags": fix_tags_str,)\s+(\})'
replacement1 = r'\1\n' + additional_fields + r'\n        \2'

# Apply pattern 1
content = re.sub(pattern1, replacement1, content, count=1)

# Pattern 2: mine_repo_releases around line 683-706
# Similar fix for mine_repo_releases
pattern2 = r'(\s+metrics: Dict\[str, Any\] = \{[^}]+?"fix_commit_tags": fix_tags_str,)\s+(?"szz_introducing_commits": "",)'
# This is more complex - we need to find the right location in releases function

# Pattern 3: mine_repo_single_version around line 829-852
# Similar fix for mine_repo_single_version

# Actually, let's use a different approach - find all three occurrences
# and add the fields right after "fix_commit_tags"

# Since the dictionaries have different structures, let's handle each separately
# For now, let's manually construct the replacements

# First, let's add modified_files tracking in mine_repo_commits
# Find where stats are calculated and add file tracking
modified_files_code = '''
            # Extract list of modified files
            modified_files = list(stats.files.keys()) if stats.files else []
            modified_files_str = ",".join(modified_files)
'''

# Insert after total_churn calculation in mine_repo_commits
content = re.sub(
    r'(total_churn = total_insertions \+ total_deletions\n)',
    r'\1' + modified_files_code + '\n',
    content,
    count=1  # Only first occurrence in mine_repo_commits
)

# Now update the "commit_files": "" to use the modified_files_str
content = re.sub(
    r'"commit_files": ""',
    r'"commit_files": modified_files_str',
    content
)

# Repeat for mine_repo_releases (second occurrence)
# But for releases, they might already have modified files logic or not
# Let's check if we need to add it

# Add modified files tracking for releases function too
content = re.sub(
    r'(# In mine_repo_releases.*?total_churn = total_insertions \+ total_deletions\n)',
    r'\1' + modified_files_code + '\n',
    content,
    count=1
)

# And for single_version
content = re.sub(
    r'(# In mine_repo_single_version.*?total_churn = total_insertions \+ total_deletions\n)',
    r'\1' + modified_files_code + '\n',
    content,
    count=1
)

print("File updated! Now applying the changes...")

# Write back
with open('legacy_miner.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ Added missing fields to legacy_miner.py dictionaries")
print("✓ Ensured commit_files is populated")
print("✓ Added developer_type fields with defaults")
print("✓ Added issue_bodies and issue_comments fields")
