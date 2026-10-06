import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../lib/api';

export default function SubmissionDetail() {
  const { id } = useParams<{ id: string }>();
  const [submission, setSubmission] = useState<any>(null);
  const [documents, setDocuments] = useState<any[]>([]);
  const [extractedData, setExtractedData] = useState<any>(null);
  const [validation, setValidation] = useState<any>(null);
  const [riskAssessment, setRiskAssessment] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('documents');
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (id) {
      fetchSubmissionDetails();
    }
  }, [id]);

  const fetchSubmissionDetails = async () => {
    try {
      const [subData, docsData] = await Promise.all([
        api.getSubmission(id!),
        api.getDocuments(id!),
      ]);
      setSubmission(subData);
      setDocuments(docsData);

      // Fetch additional data if submission is processed
      if (subData.status === 'completed') {
        const [extracted, validationData, risk] = await Promise.all([
          api.getExtractedData(id!).catch(() => null),
          api.getValidationResults(id!).catch(() => null),
          api.getRiskAssessment(id!).catch(() => null),
        ]);
        setExtractedData(extracted);
        setValidation(validationData);
        setRiskAssessment(risk);
      }
    } catch (error) {
      console.error('Failed to fetch submission details:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !id) return;

    setUploading(true);
    try {
      await api.uploadDocument(id, file);
      await fetchSubmissionDetails();
    } catch (error) {
      console.error('Failed to upload document:', error);
    } finally {
      setUploading(false);
    }
  };

  const handleProcessSubmission = async () => {
    if (!id) return;
    try {
      await api.processSubmission(id);
      await fetchSubmissionDetails();
    } catch (error) {
      console.error('Failed to process submission:', error);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!submission) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="text-center text-gray-500">Submission not found</div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          {submission.submission_name}
        </h1>
        <div className="mt-4 flex items-center space-x-4">
          <span
            className={`px-3 py-1 rounded-full text-sm font-medium ${
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
          <span className="text-sm text-gray-500 dark:text-gray-400">
            Created: {new Date(submission.created_at).toLocaleDateString()}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="card">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Insured Name
          </h3>
          <p className="mt-2 text-lg font-semibold text-gray-900 dark:text-white">
            {submission.insured_name || 'N/A'}
          </p>
        </div>
        <div className="card">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Broker Name
          </h3>
          <p className="mt-2 text-lg font-semibold text-gray-900 dark:text-white">
            {submission.broker_name || 'N/A'}
          </p>
        </div>
        <div className="card">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Documents
          </h3>
          <p className="mt-2 text-lg font-semibold text-gray-900 dark:text-white">
            {documents.length}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700 mb-6">
        <nav className="-mb-px flex space-x-8">
          {['documents', 'extracted', 'validation', 'risk'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === tab
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </nav>
      </div>

      {/* Documents Tab */}
      {activeTab === 'documents' && (
        <div className="card">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Documents
            </h2>
            <div className="flex space-x-3">
              <label className="btn-primary cursor-pointer">
                {uploading ? 'Uploading...' : 'Upload Document'}
                <input
                  type="file"
                  className="hidden"
                  onChange={handleFileUpload}
                  disabled={uploading}
                  accept=".pdf,.doc,.docx,.txt"
                />
              </label>
              {documents.length > 0 && submission.status !== 'processing' && (
                <button onClick={handleProcessSubmission} className="btn-secondary">
                  Process Submission
                </button>
              )}
            </div>
          </div>

          {documents.length > 0 ? (
            <div className="space-y-3">
              {documents.map((doc: any) => (
                <div
                  key={doc.id}
                  className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg"
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-medium text-gray-900 dark:text-white">
                        {doc.file_name}
                      </h3>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        Type: {doc.document_type || 'Unknown'} | Size:{' '}
                        {(doc.file_size / 1024).toFixed(2)} KB
                      </p>
                    </div>
                    <span
                      className={`px-2 py-1 rounded text-xs ${
                        doc.processing_status === 'completed'
                          ? 'bg-green-100 text-green-800'
                          : doc.processing_status === 'processing'
                          ? 'bg-yellow-100 text-yellow-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {doc.processing_status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              No documents uploaded yet. Upload documents to get started.
            </div>
          )}
        </div>
      )}

      {/* Extracted Data Tab */}
      {activeTab === 'extracted' && (
        <div className="card">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-6">
            Extracted Data
          </h2>
          {extractedData && extractedData.length > 0 ? (
            <div className="space-y-4">
              {extractedData.map((data: any, index: number) => (
                <div key={index} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                  <pre className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap overflow-x-auto">
                    {JSON.stringify(data.extracted_data, null, 2)}
                  </pre>
                  <div className="mt-4 text-xs text-gray-500 dark:text-gray-400">
                    Confidence: {(data.confidence_score * 100).toFixed(1)}%
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              No extracted data available. Process the submission first.
            </div>
          )}
        </div>
      )}

      {/* Validation Tab */}
      {activeTab === 'validation' && (
        <div className="card">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-6">
            Validation Results
          </h2>
          {validation && validation.length > 0 ? (
            <div className="space-y-4">
              {validation.map((result: any, index: number) => (
                <div key={index} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <span
                      className={`px-3 py-1 rounded-full text-sm font-medium ${
                        result.is_valid
                          ? 'bg-green-100 text-green-800'
                          : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {result.is_valid ? 'Valid' : 'Invalid'}
                    </span>
                  </div>
                  {result.errors && result.errors.length > 0 && (
                    <div className="mt-3">
                      <h4 className="font-medium text-red-600 mb-2">Errors:</h4>
                      <ul className="list-disc list-inside space-y-1 text-sm text-gray-700 dark:text-gray-300">
                        {result.errors.map((error: string, i: number) => (
                          <li key={i}>{error}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {result.warnings && result.warnings.length > 0 && (
                    <div className="mt-3">
                      <h4 className="font-medium text-yellow-600 mb-2">Warnings:</h4>
                      <ul className="list-disc list-inside space-y-1 text-sm text-gray-700 dark:text-gray-300">
                        {result.warnings.map((warning: string, i: number) => (
                          <li key={i}>{warning}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              No validation results available.
            </div>
          )}
        </div>
      )}

      {/* Risk Assessment Tab */}
      {activeTab === 'risk' && (
        <div className="card">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-6">
            Risk Assessment
          </h2>
          {riskAssessment ? (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
                    Risk Level
                  </h3>
                  <span
                    className={`px-3 py-1 rounded-full text-lg font-medium ${
                      riskAssessment.risk_level === 'low'
                        ? 'bg-green-100 text-green-800'
                        : riskAssessment.risk_level === 'medium'
                        ? 'bg-yellow-100 text-yellow-800'
                        : 'bg-red-100 text-red-800'
                    }`}
                  >
                    {riskAssessment.risk_level?.toUpperCase()}
                  </span>
                </div>
                <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
                    Risk Score
                  </h3>
                  <p className="text-2xl font-bold text-gray-900 dark:text-white">
                    {riskAssessment.risk_score?.toFixed(2)}
                  </p>
                </div>
              </div>
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <h3 className="font-medium text-gray-900 dark:text-white mb-3">
                  Risk Factors
                </h3>
                <pre className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                  {JSON.stringify(riskAssessment.risk_factors, null, 2)}
                </pre>
              </div>
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              No risk assessment available.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
