import Head from 'next/head';
import Link from 'next/link';

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 flex flex-col">
      <Head>
        <title>AWS Cost Analyzer</title>
      </Head>
      <header className="p-6 bg-white shadow-md">
        <h1 className="text-4xl font-bold text-indigo-600">AWS Cost Analyzer</h1>
      </header>
      <main className="flex-grow container mx-auto px-4 py-8 text-center">
        <h2 className="text-2xl text-gray-700 mb-4">Unlock deep insights into your AWS spending</h2>
        <div className="flex justify-center space-x-4">
          <Link href="/upload" className="bg-indigo-600 text-white px-6 py-3 rounded-lg shadow hover:bg-indigo-700 transition">
            Upload Data
          </Link>
          <Link href="/ask" className="border border-indigo-600 text-indigo-600 px-6 py-3 rounded-lg shadow hover:bg-indigo-100 transition">
            Ask a Question
          </Link>
        </div>
      </main>
      <footer className="p-4 text-center text-gray-500">
        © {new Date().getFullYear()} AWS Cost Analyzer
      </footer>
    </div>
  );
}