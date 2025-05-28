import Head from 'next/head';
import Link from 'next/link';
import { useState } from 'react';

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<any>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) {
      setFile(e.target.files[0]);
      setResponse(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch('http://localhost:8000/upload', { method: 'POST', body: formData });
      const data = await res.json();
      setResponse(data);
    } catch (err) {
      setResponse({ error: 'Upload failed.' });
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 flex flex-col">
      <Head>
        <title>Upload Data - AWS Cost Analyzer</title>
      </Head>
      <header className="p-6 bg-white shadow-md">
        <h1 className="text-3xl font-semibold text-indigo-600">Upload AWS Billing Data</h1>
        <nav className="mt-4 space-x-4">
          <Link href="/" className="text-indigo-500 hover:underline">
            Home
          </Link>
          <Link href="/ask" className="text-indigo-500 hover:underline">
            Ask
          </Link>
        </nav>
      </header>
      <main className="flex-grow container mx-auto px-4 py-8">
        <form onSubmit={handleSubmit} className="bg-white p-6 rounded-lg shadow-md flex flex-col gap-4">
          <input
            type="file"
            accept=".csv,.xls,.xlsx"
            onChange={handleChange}
            className="border border-gray-300 rounded px-3 py-2"
          />
          <button
            type="submit"
            disabled={!file || loading}
            className="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700 transition disabled:opacity-50"
          >
            {loading ? 'Uploading...' : 'Upload File'}
          </button>
        </form>
        {response && (
          <div className="mt-6 bg-white p-4 rounded-lg shadow-md">
            <h2 className="text-xl font-medium text-gray-700 mb-2">Response</h2>
            <pre className="bg-gray-100 p-4 rounded">{JSON.stringify(response, null, 2)}</pre>
          </div>
        )}
      </main>
      <footer className="p-4 text-center text-gray-500">
        © {new Date().getFullYear()} AWS Cost Analyzer
      </footer>
    </div>
  );
}