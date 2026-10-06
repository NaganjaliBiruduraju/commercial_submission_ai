import { useEffect, useState } from 'react';
import { api } from '../lib/api';

export default function KnowledgeBase() {
  const [articles, setArticles] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newArticle, setNewArticle] = useState({
    title: '',
    content: '',
    category: '',
    tags: '',
  });

  useEffect(() => {
    fetchArticles();
  }, []);

  const fetchArticles = async () => {
    try {
      const data = await api.getKnowledgeArticles(0, 50);
      setArticles(data);
    } catch (error) {
      console.error('Failed to fetch articles:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setSearching(true);
    try {
      const results = await api.searchKnowledge(searchQuery, 10);
      setSearchResults(results);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setSearching(false);
    }
  };

  const handleCreateArticle = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createKnowledgeArticle({
        title: newArticle.title,
        content: newArticle.content,
        category: newArticle.category || undefined,
        tags: newArticle.tags
          ? newArticle.tags.split(',').map((t) => t.trim())
          : undefined,
      });
      setShowCreateModal(false);
      setNewArticle({ title: '', content: '', category: '', tags: '' });
      fetchArticles();
    } catch (error) {
      console.error('Failed to create article:', error);
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
          Knowledge Base
        </h1>
        <p className="mt-2 text-gray-600 dark:text-gray-400">
          Search guidelines, regulations, and best practices
        </p>
      </div>

      {/* Search Bar */}
      <div className="card mb-8">
        <form onSubmit={handleSearch} className="flex space-x-4">
          <input
            type="text"
            placeholder="Search knowledge base using natural language..."
            className="input-field flex-1"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <button
            type="submit"
            disabled={searching}
            className="btn-primary disabled:opacity-50"
          >
            {searching ? 'Searching...' : 'Search'}
          </button>
        </form>
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
          Powered by RAG (Retrieval Augmented Generation) with semantic search
        </p>
      </div>

      {/* Search Results */}
      {searchResults.length > 0 && (
        <div className="mb-8">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Search Results
            </h2>
            <button
              onClick={() => setSearchResults([])}
              className="text-sm text-blue-600 hover:text-blue-700"
            >
              Clear Results
            </button>
          </div>
          <div className="space-y-4">
            {searchResults.map((result: any) => (
              <div key={result.id} className="card hover:shadow-lg transition-shadow">
                <div className="flex justify-between items-start mb-3">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                    {result.title}
                  </h3>
                  <span className="text-sm text-blue-600 font-medium">
                    {(result.similarity_score * 100).toFixed(1)}% match
                  </span>
                </div>
                <p className="text-gray-700 dark:text-gray-300 mb-3">
                  {result.content.substring(0, 300)}...
                </p>
                {result.category && (
                  <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs rounded">
                    {result.category}
                  </span>
                )}
                {result.tags && result.tags.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {result.tags.map((tag: string, i: number) => (
                      <span
                        key={i}
                        className="px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 text-xs rounded"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* All Articles */}
      <div>
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            All Articles
          </h2>
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-primary"
          >
            Create Article
          </button>
        </div>

        {articles.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {articles.map((article) => (
              <div key={article.id} className="card">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  {article.title}
                </h3>
                <p className="text-gray-700 dark:text-gray-300 text-sm mb-3">
                  {article.content.substring(0, 150)}...
                </p>
                {article.category && (
                  <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs rounded">
                    {article.category}
                  </span>
                )}
                {article.tags && article.tags.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {article.tags.map((tag: string, i: number) => (
                      <span
                        key={i}
                        className="px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 text-xs rounded"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="card text-center py-12">
            <p className="text-gray-500 dark:text-gray-400 mb-4">
              No articles found. Create your first article to build your knowledge base.
            </p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="btn-primary"
            >
              Create Article
            </button>
          </div>
        )}
      </div>

      {/* Create Article Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-2xl w-full max-h-screen overflow-y-auto">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              Create Knowledge Article
            </h2>
            <form onSubmit={handleCreateArticle} className="space-y-4">
              <div>
                <label htmlFor="title" className="label">
                  Title *
                </label>
                <input
                  id="title"
                  type="text"
                  required
                  className="input-field"
                  value={newArticle.title}
                  onChange={(e) =>
                    setNewArticle({ ...newArticle, title: e.target.value })
                  }
                />
              </div>

              <div>
                <label htmlFor="content" className="label">
                  Content *
                </label>
                <textarea
                  id="content"
                  required
                  rows={8}
                  className="input-field"
                  value={newArticle.content}
                  onChange={(e) =>
                    setNewArticle({ ...newArticle, content: e.target.value })
                  }
                />
              </div>

              <div>
                <label htmlFor="category" className="label">
                  Category
                </label>
                <input
                  id="category"
                  type="text"
                  className="input-field"
                  placeholder="e.g., Guidelines, Regulations, Best Practices"
                  value={newArticle.category}
                  onChange={(e) =>
                    setNewArticle({ ...newArticle, category: e.target.value })
                  }
                />
              </div>

              <div>
                <label htmlFor="tags" className="label">
                  Tags (comma-separated)
                </label>
                <input
                  id="tags"
                  type="text"
                  className="input-field"
                  placeholder="e.g., property, liability, workers-comp"
                  value={newArticle.tags}
                  onChange={(e) =>
                    setNewArticle({ ...newArticle, tags: e.target.value })
                  }
                />
              </div>

              <div className="flex space-x-3 mt-6">
                <button type="submit" className="btn-primary flex-1">
                  Create Article
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
