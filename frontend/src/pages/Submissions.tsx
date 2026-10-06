import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';

export default function Submissions() {
  const [submissions, setSubmissions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newSubmission, setNewSubmission] = useState({
    submission_name: '',
    insured_name: '',
    broker_name: '',
  });

  useEffect(() => {
    fetchSubmissions();
  }, []);

  const fetchSubmissions = async () => {
    try {
      const data = await api.getSubmissions(0, 100);
      setSubmissions(data);
    } catch (error) {
      console.error('Failed to fetch submissions:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateSubmission = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createSubmission({
        submission_name: newSubmission.submission_name,
        insured_name: newSubmission.insured_name || undefined,
        broker_name: newSubmission.broker_name || undefined,
      });
      setShowCreateModal(false);
      setNewSubmission({ submission_name: '', insured_name: '', broker_name: '' });
      fetchSubmissions();
    } catch (error) {
      console.error('Failed to create submission:', error);
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
      <div className="mb-8 flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            Submissions
          </h1>
          <p className="mt-2 text-gray-600 dark:text-gray-400">
            Manage and process insurance submissions
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="btn-primary"
        >
          Create New Submission
        </button>
      </div>

      {submissions.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {submissions.map((submission) => (
            <Link
              key={submission.id}
              to={`/submissions/${submission.id}`}
              className="card hover:shadow-lg transition-shadow"
            >
              <div className="mb-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  {submission.submission_name}
                </h3>
                <div className="space-y-1 text-sm">
                  <p className="text-gray-600 dark:text-gray-400">
                    <span className="font-medium">Insured:</span>{' '}
                    {submission.insured_name || 'N/A'}
                  </p>
                  <p className="text-gray-600 dark:text-gray-400">
                    <span className="font-medium">Broker:</span>{' '}
                    {submission.broker_name || 'N/A'}
                  </p>
                </div>
              </div>

              <div className="flex justify-between items-center">
                <span
                  className={`px-3 py-1 rounded-full text-xs font-medium ${
                    submission.status === 'completed'
                      ? 'bg-green-100 text-green-800'
                      : submission.status === 'processing'
                      ? 'bg-yellow-100 text-yellow-800'
                      : submission.status === 'failed'
                      ? 'bg-red-100 text-red-800'
                      : 'bg-gray-100 text-gray-800'
                  }`}
                >
                  {submission.status}
                </span>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {new Date(submission.created_at).toLocaleDateString()}
                </span>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="card text-center py-12">
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            No submissions found. Create your first submission to get started.
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-primary"
          >
            Create New Submission
          </button>
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              Create New Submission
            </h2>
            <form onSubmit={handleCreateSubmission} className="space-y-4">
              <div>
                <label htmlFor="submission_name" className="label">
                  Submission Name *
                </label>
                <input
                  id="submission_name"
                  type="text"
                  required
                  className="input-field"
                  value={newSubmission.submission_name}
                  onChange={(e) =>
                    setNewSubmission({
                      ...newSubmission,
                      submission_name: e.target.value,
                    })
                  }
                />
              </div>

              <div>
                <label htmlFor="insured_name" className="label">
                  Insured Name
                </label>
                <input
                  id="insured_name"
                  type="text"
                  className="input-field"
                  value={newSubmission.insured_name}
                  onChange={(e) =>
                    setNewSubmission({
                      ...newSubmission,
                      insured_name: e.target.value,
                    })
                  }
                />
              </div>

              <div>
                <label htmlFor="broker_name" className="label">
                  Broker Name
                </label>
                <input
                  id="broker_name"
                  type="text"
                  className="input-field"
                  value={newSubmission.broker_name}
                  onChange={(e) =>
                    setNewSubmission({
                      ...newSubmission,
                      broker_name: e.target.value,
                    })
                  }
                />
              </div>

              <div className="flex space-x-3 mt-6">
                <button type="submit" className="btn-primary flex-1">
                  Create
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="btn-secondary flex-1"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
