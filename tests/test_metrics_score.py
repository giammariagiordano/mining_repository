import unittest
from datetime import datetime
from models.metrics import CommitMetrics

class TestCommitMetricsScore(unittest.TestCase):
    def test_metrics_score(self):
        metrics = CommitMetrics(
            project_name="test_project",
            repo_path="/tmp/test",
            branch="main",
            commit_sha="123456",
            commit_date=datetime.now(),
            author_name="Test Author",
            commit_message="Test message",
            commit_insertions=10,
            commit_deletions=5,
            commit_files_changed=1,
            commit_churn=15,
            repo_stars=100,
            repo_forks=10,
            repo_loc=1000,
            repo_commit_count=50,
            repo_contributors=5,
            ref_type="commit",
            ref_name="123456",
            fix_commit=0,
            fix_commit_tags="",
            ml_score=10,
            se_score=5
        )
        
        data = metrics.to_dict()
        self.assertEqual(data["ml_score"], 10)
        self.assertEqual(data["se_score"], 5)
        
    def test_metrics_default_score(self):
        metrics = CommitMetrics(
            project_name="test_project",
            repo_path="/tmp/test",
            branch="main",
            commit_sha="123456",
            commit_date=datetime.now(),
            author_name="Test Author",
            commit_message="Test message",
            commit_insertions=10,
            commit_deletions=5,
            commit_files_changed=1,
            commit_churn=15,
            repo_stars=100,
            repo_forks=10,
            repo_loc=1000,
            repo_commit_count=50,
            repo_contributors=5,
            ref_type="commit",
            ref_name="123456",
            fix_commit=0,
            fix_commit_tags=""
        )
        
        data = metrics.to_dict()
        self.assertEqual(data["ml_score"], 0)
        self.assertEqual(data["se_score"], 0)

if __name__ == '__main__':
    unittest.main()
