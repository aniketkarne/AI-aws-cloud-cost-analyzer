import Head from 'next/head';
import { useState } from 'react';
import Link from 'next/link';
import CostChart from '../components/CostChart';

export default function AskPage() {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question) return;
    setLoading(true);
    setResult(null);
    try {
      const response = await fetch('http://localhost:8000/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      const data = await response.json();
      setResult(data);
    } catch (err) {
      setResult({ error: 'Failed to fetch answer.' });
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 flex flex-col">
      <Head>
        <title>Ask a Question - AWS Cost Analyzer</title>
      </Head>
      <header className="p-6 bg-white shadow-md flex justify-between items-center">
        <h1 className="text-3xl font-semibold text-indigo-600">AWS Cost Analyzer</h1>
        <nav className="space-x-4">
          <Link href="/" className="text-indigo-500 hover:underline">Home</Link>
          <Link href="/upload" className="text-indigo-500 hover:underline">Upload</Link>
        </nav>
      </header>
      <main className="flex-grow container mx-auto px-4 py-8">
        <form onSubmit={handleAsk} className="bg-white p-6 rounded-lg shadow-md flex flex-col gap-4">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask your AWS cost question..."
            className="border border-gray-300 rounded p-3 h-24 resize-none focus:outline-indigo-500"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={!question || loading}
            className="self-end bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700 transition disabled:opacity-50"
          >
            {loading ? 'Thinking...' : 'Ask'}
          </button>
        </form>
        {result && (
          <div className="mt-6 space-y-6">
            <div className="bg-white p-4 rounded-lg shadow-md">
              <h2 className="text-xl font-medium text-gray-700">Answer</h2>
              <p className="mt-2 text-gray-800">{result.answer || result.error}</p>
            </div>
            {result.data && (
              <div className="bg-white p-4 rounded-lg shadow-md">
                <h3 className="text-lg font-medium text-gray-700 mb-2">Cost Breakdown</h3>
                <CostChart data={result.data} labelKey="service" valueKey="cost" title="Cost by Service" />
              </div>
            )}
          </div>
        )}
      </main>
      <footer className="p-4 text-center text-gray-500">
        © {new Date().getFullYear()} AWS Cost Analyzer
      </footer>
    </div>
  );
}