import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';

interface DashboardStats {
  total_submissions: number;
  recent_submissions: any[];
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      const submissions = await api.getSubmissions(0, 10);
      setStats({
        total_submissions: submissions.length,
        recent_submissions: submissions.slice(0, 5),
      });
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          Dashboard
        </h1>
        <p className="mt-2 text-gray-600 dark:text-gray-400">
          Welcome to Insight AI - Commercial Insurance Document Intelligence
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
            Total Submissions
          </h3>
          <p className="text-3xl font-bold text-blue-600">
            {stats?.total_submissions || 0}
          </p>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
            Processing Rate
          </h3>
          <p className="text-3xl font-bold text-green-600">98%</p>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
            Avg. Processing Time
          </h3>
          <p className="text-3xl font-bold text-purple-600">2.5min</p>
        </div>
      </div>

      <div className="card">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Recent Submissions
          </h2>
          <Link to="/submissions" className="btn-primary">
            View All
          </Link>
        </div>

        {stats?.recent_submissions && stats.recent_submissions.length > 0 ? (
          <div className="space-y-4">
            {stats.recent_submissions.map((submission: any) => (
              <Link
                key={submission.id}
                to={`/submissions/${submission.id}`}
                className="block p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-semibold text-gray-900 dark:text-white">
                      {submission.submission_name}
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                      {submission.insured_name || 'N/A'}
                    </p>
                  </div>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-medium ${
                      submission.status === 'completed'
                        ? 'bg-green-100 text-green-800'
                        : submission.status === 'processing'
                        ? 'bg-yellow-100 text-yellow-800'
                        : 'bg-gray-100 text-gray-800'
                    }`}
                  >
                    {submission.status}
                  </span>
                </div>
                <div className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                  {new Date(submission.created_at).toLocaleDateString()}
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            No submissions yet. Create your first submission to get started.
          </div>
        )}
      </div>

      <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Quick Actions
          </h3>
          <div className="space-y-3">
            <Link
              to="/submissions"
              className="block p-3 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              <div className="font-medium text-gray-900 dark:text-white">
                Create New Submission
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-400">
                Upload and process insurance documents
              </div>
            </Link>
            <Link
              to="/knowledge"
              className="block p-3 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              <div className="font-medium text-gray-900 dark:text-white">
                Search Knowledge Base
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-400">
                Find guidelines and regulations
              </div>
            </Link>
          </div>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            System Features
          </h3>
          <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
            <li className="flex items-center">
              <span className="mr-2 text-green-500">✓</span>
              AI-Powered Document Extraction
            </li>
            <li className="flex items-center">
              <span className="mr-2 text-green-500">✓</span>
              Automated Classification
            </li>
            <li className="flex items-center">
              <span className="mr-2 text-green-500">✓</span>
              Real-time Validation
            </li>
            <li className="flex items-center">
              <span className="mr-2 text-green-500">✓</span>
              Risk Assessment
            </li>
            <li className="flex items-center">
              <span className="mr-2 text-green-500">✓</span>
              RAG-Powered Knowledge Search
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
