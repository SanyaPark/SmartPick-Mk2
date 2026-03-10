import React, { useState } from 'react';
import Head from 'next/head';
import Image from 'next/image';
import dynamic from 'next/dynamic';
import SwiperCarousel, { OrbitItem } from '../components/SwiperCarousel';
import { CARDS } from '../components/CardCarousel';

const ChatKitWrapper = dynamic(() => import('../components/ChatKitWrapper'), {
  ssr: false,
});

export default function Home() {
  const [isSpinning, setIsSpinning] = useState(false);
  const [highlightedCardId, setHighlightedCardId] = useState<string | null>(null);

  const orbitItems: OrbitItem[] = CARDS.map(card => ({
    id: card.id,
    eyebrow: card.company,
    title: card.name,
    description: `${card.company} ${card.name} offers exclusive benefits and rewards tailored for you.`,
    meta: "Credit Card",
    image: card.image,
  }));

  const handleCardSelected = (cardId: string | null) => {
    setHighlightedCardId(cardId);
    setIsSpinning(false);
  };

  return (
    <div className="flex flex-col min-h-[100dvh] w-full bg-customNavy font-sans text-white overflow-hidden relative pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]">
      <Head>
        <title>SmartPick - AI Card Recommender</title>
        <meta name="description" content="Find your perfect credit card with AI" />
      </Head>

      {/* Fixed Background Layer */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute top-0 left-1/4 w-[40vw] h-[40vw] bg-customTeal/10 rounded-full blur-[100px]" />
        <div className="absolute top-1/4 right-1/4 w-[30vw] h-[30vw] bg-customGreen/10 rounded-full blur-[100px]" />
        <div className="absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-[#0b1126]/80 via-transparent to-transparent" />
        <div className="absolute inset-x-0 bottom-0 h-64 bg-gradient-to-t from-[#0b1126]/80 via-transparent to-transparent" />
      </div>

      {/* Fixed Header */}
      <header className="flex-none relative z-50 w-full border-b border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_10px_40px_rgba(0,0,0,0.35)]">
        <div className="max-w-5xl mx-auto px-6 py-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <div className="relative w-10 h-10 rounded-xl overflow-hidden border border-white/10 bg-white/10">
              <Image 
                src="/logo.png"
                alt="SmartPick logo"
                fill
                sizes="40px"
                className="object-cover"
              />
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-[0.3em] text-white/60">SmartPick</p>
              <h1 className="text-lg font-semibold text-white">Concierge Intelligence</h1>
            </div>
          </div>
          <div className="text-xs text-white/70 hidden sm:block text-right">
            <p className="font-semibold text-white">Always-on advisor</p>
            <p>Personalized card guidance</p>
          </div>
        </div>
      </header>

      <main className="flex-1 relative z-40 w-full flex flex-col items-center justify-start pt-6 sm:pt-10 pb-16 px-3 sm:px-6 overflow-y-auto">
        <div className="w-full max-w-5xl relative rounded-[3rem] border border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_0_80px_rgba(0,0,0,0.4)] overflow-hidden flex flex-col">
          
          <div className="relative w-full h-[420px] sm:h-[520px] lg:h-[560px] flex flex-col items-center pt-10 pb-24 sm:pb-28 bg-gradient-to-b from-white/5 via-transparent to-transparent">
            <div className="text-center mb-4 z-10 relative px-4">
              <h2 className="text-2xl md:text-4xl font-extrabold tracking-tight text-white mb-2 opacity-90 drop-shadow-sm">
                {isSpinning ? 'Analyzing your preferences...' : highlightedCardId ? 'We found a match!' : 'SmartPick AI'}
              </h2>
              <p className="text-white/60 text-sm md:text-base max-w-xl mx-auto">
                Discover the perfect card for your lifestyle with our AI-powered recommendations.
              </p>
            </div>
            
            <div className="absolute inset-0 top-16 sm:top-20 w-full flex items-center justify-center">
              <SwiperCarousel 
                items={orbitItems}
                activeId={highlightedCardId}
                orbitSpeed={isSpinning ? 2 : 0.1}
                radius={280}
                className="w-full h-full"
              />
            </div>
          </div>

          <div className="relative z-20 mt-0 px-3 sm:px-8 pb-12 sm:pb-16 w-full flex justify-center border-t border-white/10 bg-white/5">
            <div className="w-full max-w-4xl shadow-2xl transition-all duration-500 ease-[cubic-bezier(.4,0,.2,1)]">
              <ChatKitWrapper 
                onSpin={() => setIsSpinning(true)}
                onCardSelected={handleCardSelected}
              />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
