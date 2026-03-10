import Head from 'next/head';

export default function RecommendPage() {
  return (
    <div className="min-h-screen bg-customNavy text-white flex items-center justify-center p-8">
      <Head>
        <title>Recommendations Coming Soon</title>
        <meta name="robots" content="noindex" />
      </Head>
      <div className="text-center space-y-3 max-w-md">
        <h1 className="text-3xl font-bold tracking-tight">Recommendations Page</h1>
        <p className="text-white/70">
          We&apos;re building a richer recommendations experience. Check back soon!
        </p>
      </div>
    </div>
  );
}
