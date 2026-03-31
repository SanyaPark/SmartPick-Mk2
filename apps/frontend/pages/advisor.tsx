import React, { useState } from 'react';
import Head from 'next/head';
import Image from 'next/image';
import Link from 'next/link';
import { ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
import { CARDS } from '../components/CardCarousel';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';

// ── Button config mirrors QUERIES_STANDALONE / QUERIES_DETAILS ──────────────

const STANDALONE_BUTTONS = [
  { key: 'reviews',      label: '후기 보기' },
  { key: 'how_to_apply', label: '신청 방법' },
] as const;

const DETAIL_BUTTONS = [
  { key: 'credit_fees',        label: '수수료' },
  { key: 'international_fees', label: '해외 이용' },
  { key: 'late_payment',       label: '연체 안내' },
  { key: 'revolving',          label: '리볼빙' },
] as const;

type QueryKey =
  | (typeof STANDALONE_BUTTONS)[number]['key']
  | (typeof DETAIL_BUTTONS)[number]['key'];

// ── Minimal markdown renderer ────────────────────────────────────────────────

function MarkdownLine({ line }: { line: string }) {
  const parts = line.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith('**') && part.endsWith('**')
          ? <strong key={i} className="font-semibold text-white">{part.slice(2, -2)}</strong>
          : <span key={i}>{part}</span>
      )}
    </>
  );
}

function MarkdownResponse({ text }: { text: string }) {
  const lines = text.split('\n');
  return (
    <div className="space-y-1 text-sm leading-relaxed">
      {lines.map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={i} className="h-2" />;

        // Section header: [TEXT] or **[TEXT]**
        if (/^\[.+\]$/.test(trimmed) || /^\*\*\[.+\]\*\*$/.test(trimmed)) {
          const label = trimmed.replace(/\*\*/g, '').replace(/[\[\]]/g, '');
          return (
            <p key={i} className="font-bold text-customTeal mt-4 mb-1 uppercase tracking-wide text-xs">
              {label}
            </p>
          );
        }

        // Bullet line
        if (trimmed.startsWith('•') || trimmed.startsWith('-')) {
          const content = trimmed.replace(/^[•\-]\s*/, '');
          return (
            <div key={i} className="flex gap-2 pl-2">
              <span className="text-customTeal mt-0.5 shrink-0">•</span>
              <span className="flex-1 text-white/80"><MarkdownLine line={content} /></span>
            </div>
          );
        }

        return (
          <p key={i} className="text-white/80">
            <MarkdownLine line={line} />
          </p>
        );
      })}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function AdvisorPage() {
  const [selectedCardId, setSelectedCardId] = useState('');
  const [detailsOpen, setDetailsOpen]       = useState(false);
  const [activeQuery, setActiveQuery]       = useState<QueryKey | null>(null);
  const [answer, setAnswer]                 = useState<string | null>(null);
  const [loading, setLoading]               = useState(false);
  const [error, setError]                   = useState<string | null>(null);

  const selectedCard = CARDS.find(c => c.id === selectedCardId);

  async function ask(queryType: QueryKey) {
    if (!selectedCard) return;
    setActiveQuery(queryType);
    setAnswer(null);
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/advisor/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          card_name:    selectedCard.name,
          card_company: selectedCard.company,
          query_type:   queryType,
        }),
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await res.json();
      setAnswer(data.answer);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }

  function onCardChange(id: string) {
    setSelectedCardId(id);
    setAnswer(null);
    setActiveQuery(null);
    setError(null);
  }

  const btnBase =
    'px-5 py-2.5 rounded-xl text-sm font-medium transition-all border disabled:opacity-40 disabled:cursor-not-allowed';
  const btnActive =
    'bg-customTeal/25 border-customTeal text-white';
  const btnIdle =
    'bg-white/10 border-white/15 text-white/80 hover:bg-white/15 hover:text-white';
  const btnIdleSub =
    'bg-white/5 border-white/10 text-white/70 hover:bg-white/10 hover:text-white';

  return (
    <div className="flex flex-col min-h-[100dvh] w-full bg-customNavy font-sans text-white relative overflow-hidden">
      <Head>
        <title>SmartPick – Card Advisor</title>
        <meta name="description" content="Ask anything about your selected card" />
      </Head>

      {/* Background glow */}
      <div className="absolute inset-0 pointer-events-none z-0">
        <div className="absolute top-0 left-1/4 w-[40vw] h-[40vw] bg-customTeal/10 rounded-full blur-[100px]" />
        <div className="absolute top-1/4 right-1/4 w-[30vw] h-[30vw] bg-customGreen/10 rounded-full blur-[100px]" />
      </div>

      {/* Header */}
      <header className="flex-none relative z-50 w-full border-b border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_10px_40px_rgba(0,0,0,0.35)]">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="relative w-10 h-10 rounded-xl overflow-hidden border border-white/10 bg-white/10">
              <Image src="/logo.png" alt="SmartPick logo" fill sizes="40px" className="object-cover" />
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-[0.3em] text-white/60">SmartPick</p>
              <h1 className="text-lg font-semibold text-white">Card Advisor</h1>
            </div>
          </div>
          <Link href="/" className="text-xs text-white/50 hover:text-white/80 transition-colors">
            ← Back
          </Link>
        </div>
      </header>

      <main className="flex-1 relative z-10 w-full flex flex-col items-center pt-8 pb-16 px-4">
        <div className="w-full max-w-3xl space-y-5">

          {/* Card selector */}
          <section className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl p-6">
            <label className="block text-[10px] uppercase tracking-widest text-white/50 mb-3">
              카드 선택
            </label>
            <div className="relative">
              <select
                className="w-full bg-white/10 border border-white/15 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-customTeal/50 appearance-none cursor-pointer"
                value={selectedCardId}
                onChange={e => onCardChange(e.target.value)}
              >
                <option value="" className="bg-customNavy text-white/60">카드를 선택하세요</option>
                {CARDS.map(card => (
                  <option key={card.id} value={card.id} className="bg-customNavy">
                    {card.company} – {card.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={16} className="absolute right-4 top-1/2 -translate-y-1/2 text-white/40 pointer-events-none" />
            </div>
          </section>

          {/* Action buttons */}
          {selectedCard && (
            <section className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl p-6 space-y-4">

              {/* Standalone buttons */}
              <div className="flex gap-3 flex-wrap">
                {STANDALONE_BUTTONS.map(btn => (
                  <button
                    key={btn.key}
                    onClick={() => ask(btn.key)}
                    disabled={loading}
                    className={`${btnBase} ${activeQuery === btn.key ? btnActive : btnIdle}`}
                  >
                    {btn.label}
                  </button>
                ))}
              </div>

              {/* Details accordion */}
              <div>
                <button
                  onClick={() => setDetailsOpen(o => !o)}
                  disabled={loading}
                  className={`${btnBase} flex items-center gap-1.5 ${detailsOpen ? btnActive : btnIdle}`}
                >
                  추가 정보
                  {detailsOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>

                {detailsOpen && (
                  <div className="flex gap-3 flex-wrap mt-3">
                    {DETAIL_BUTTONS.map(btn => (
                      <button
                        key={btn.key}
                        onClick={() => ask(btn.key)}
                        disabled={loading}
                        className={`${btnBase} ${activeQuery === btn.key ? btnActive : btnIdleSub}`}
                      >
                        {btn.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Response */}
          {(loading || answer || error) && (
            <section className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl p-6 min-h-[120px]">
              {loading && (
                <div className="flex items-center gap-3 text-white/50 text-sm">
                  <Loader2 size={16} className="animate-spin text-customTeal" />
                  답변을 가져오는 중…
                </div>
              )}
              {error && !loading && (
                <p className="text-red-400 text-sm">{error}</p>
              )}
              {answer && !loading && (
                <MarkdownResponse text={answer} />
              )}
            </section>
          )}

        </div>
      </main>
    </div>
  );
}
