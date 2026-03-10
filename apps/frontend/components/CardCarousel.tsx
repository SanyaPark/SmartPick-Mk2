import React, { useEffect, useRef } from 'react';
import { motion, useAnimation, useMotionValue } from 'framer-motion';
import Image from 'next/image';

export type CardData = {
  id: string;
  company: string;
  name: string;
  color: string;
  gradient: string;
  image: string;
  aliases?: string[];
};

const FALLBACK_CARD_IMAGE = '/logo.png';

const normalizeCardKey = (value: string | undefined | null): string =>
  (value || '')
    .toLowerCase()
    .replace(/[^a-z0-9가-힣]/g, '');

export const findCardIdByName = (cardName: string | undefined | null): string | null => {
  const incoming = normalizeCardKey(cardName);
  if (!incoming) return null;

  for (const card of CARDS) {
    const candidates = [card.name, ...(card.aliases || [])].map(normalizeCardKey);
    if (candidates.some(candidate => candidate === incoming)) {
      return card.id;
    }
  }

  for (const card of CARDS) {
    const candidates = [card.name, ...(card.aliases || [])].map(normalizeCardKey);
    if (candidates.some(candidate => incoming.includes(candidate) || candidate.includes(incoming))) {
      return card.id;
    }
  }

  return null;
};

export const CARDS: CardData[] = [
  { id: 's-01', company: 'Shinhan', name: '신한카드 Mr.Life', color: 'indigo', gradient: 'bg-gradient-to-br from-indigo-600 via-purple-600 to-purple-800', image: '/cards/shinhanmrlife.png', aliases: ['Mr.Life'] },
  { id: 's-02', company: 'Shinhan', name: '신한카드 Deep Dream', color: 'indigo', gradient: 'bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-700', image: '/cards/shinhandeepdream.png', aliases: ['Deep Dream'] },
  { id: 's-03', company: 'Shinhan', name: '신한카드 Deep Dream Platinum+', color: 'indigo', gradient: 'bg-gradient-to-br from-violet-600 via-indigo-600 to-blue-700', image: '/cards/shinhandeepdreamplatinum+.png', aliases: ['Deep Dream Platinum+'] },
  { id: 's-04', company: 'Shinhan', name: '신한카드 Deep Oil', color: 'indigo', gradient: 'bg-gradient-to-br from-blue-700 via-indigo-700 to-slate-800', image: '/cards/shinhandeepoil.png', aliases: ['Deep Oil'] },
  { id: 's-05', company: 'Shinhan', name: '신한카드 Discount Plan+', color: 'indigo', gradient: 'bg-gradient-to-br from-indigo-700 via-slate-700 to-zinc-800', image: '/cards/shinhandiscountplan+.png', aliases: ['Discount Plan+'] },
  { id: 's-06', company: 'Shinhan', name: '신한카드 POINT Plan', color: 'indigo', gradient: 'bg-gradient-to-br from-purple-600 via-indigo-600 to-blue-800', image: '/cards/shinhanpointplan.png', aliases: ['Point Plan', 'POINT Plan'] },
  { id: 's-07', company: 'Shinhan', name: '신한카드 Simple / Simple+', color: 'indigo', gradient: 'bg-gradient-to-br from-slate-600 via-indigo-600 to-purple-700', image: '/cards/shinhanplus.png', aliases: ['Simple', 'Simple+'] },
  { id: 's-08', company: 'Shinhan', name: '신한카드 YOLO i', color: 'indigo', gradient: 'bg-gradient-to-br from-pink-600 via-purple-600 to-indigo-700', image: '/cards/shinhanyoloi.png', aliases: ['YOLO', 'YOLO i'] },
  { id: 's-09', company: 'Shinhan', name: '신한카드 The CLASSIC+', color: 'indigo', gradient: 'bg-gradient-to-br from-indigo-800 via-slate-700 to-zinc-900', image: '/cards/shinhantheclassic+.png', aliases: ['The CLASSIC+'] },
  { id: 's-10', company: 'Shinhan', name: '신한카드 SOL 트래블 체크', color: 'indigo', gradient: 'bg-gradient-to-br from-sky-600 via-indigo-600 to-blue-900', image: '/cards/shinhansoltravelcheck.png', aliases: ['SOL 트래블 체크'] },
  { id: 'k-01', company: 'KB', name: 'KB 국민 My WE:SH 카드', color: 'yellow', gradient: 'bg-gradient-to-br from-yellow-500 via-amber-500 to-orange-600', image: '/cards/kbmywesh.png', aliases: ['KB My WE:SH 카드', 'KB국민 My WE:SH(마이 위시)', 'My WE:SH'] },
  { id: 'k-02', company: 'KB', name: 'KB 국민 청춘대로 톡톡카드', color: 'yellow', gradient: 'bg-gradient-to-br from-amber-400 via-yellow-500 to-orange-500', image: '/cards/kbccdl.png', aliases: ['KB 청춘대로 톡톡카드', 'KB국민 청춘대로 톡톡카드', '톡톡카드'] },
  { id: 'k-03', company: 'KB', name: 'KB 탄탄대로 Miz&Mr 카드', color: 'yellow', gradient: 'bg-gradient-to-br from-orange-500 via-amber-500 to-yellow-600', image: '/cards/kbtantanmiz&mr.png', aliases: ['KB 탄탄대로 Miz&Mr', 'KB국민 탄탄대로 Biz카드', 'Miz&Mr'] },
  { id: 'k-04', company: 'KB', name: 'KB Easy Pick 카드', color: 'yellow', gradient: 'bg-gradient-to-br from-amber-500 via-orange-500 to-red-500', image: '/cards/kbeasypick.png', aliases: ['KB국민 Easy Pick카드', 'Easy Pick'] },
  { id: 'k-05', company: 'KB', name: 'KB The Easy 카드', color: 'yellow', gradient: 'bg-gradient-to-br from-yellow-600 via-orange-500 to-amber-600', image: '/cards/kbeasy.png', aliases: ['KB국민 The Easy카드', 'The Easy'] },
  { id: 'k-06', company: 'KB', name: 'KB FINETECH 카드', color: 'yellow', gradient: 'bg-gradient-to-br from-amber-600 via-orange-600 to-red-600', image: '/cards/kbfinetech.png', aliases: ['FINETECH'] },
  { id: 'k-07', company: 'KB', name: 'KB 직장인 보너스 체크카드', color: 'yellow', gradient: 'bg-gradient-to-br from-yellow-500 via-amber-400 to-orange-500', image: '/cards/kbworkerbonuscheck.png', aliases: ['KB국민 직장인보너스 체크카드', '직장인 보너스 체크카드'] },
  { id: 'k-08', company: 'KB', name: 'KB Star 카드', color: 'yellow', gradient: 'bg-gradient-to-br from-orange-400 via-amber-500 to-yellow-600', image: '/cards/kbstar.png', aliases: ['KB국민카드 BeV III', 'KB국민 Star 카드', 'Star'] },
  { id: 'k-09', company: 'KB', name: 'KB 국민 굿데이 카드', color: 'yellow', gradient: 'bg-gradient-to-br from-yellow-400 via-amber-500 to-orange-600', image: '/cards/kbgoodday.png', aliases: ['KB국민 굿데이올림카드', '굿데이'] },
  { id: 'k-10', company: 'KB', name: 'KB 마이원 카드', color: 'yellow', gradient: 'bg-gradient-to-br from-amber-500 via-yellow-500 to-lime-500', image: '/cards/kbmyone.png', aliases: ['마이원'] },
  { id: 'h-01', company: 'Hyundai', name: '현대카드 M', color: 'blue', gradient: 'bg-gradient-to-br from-blue-600 via-blue-500 to-blue-800', image: '/cards/hyundaim.png', aliases: ['현대카드M'] },
  { id: 'h-02', company: 'Hyundai', name: '현대카드 M BOOST', color: 'blue', gradient: 'bg-gradient-to-br from-blue-500 via-indigo-500 to-indigo-700', image: '/cards/hyundaimboost.png', aliases: ['M BOOST'] },
  { id: 'h-03', company: 'Hyundai', name: '현대카드 X', color: 'blue', gradient: 'bg-gradient-to-br from-cyan-500 via-blue-500 to-blue-700', image: '/cards/hyundaix.png', aliases: ['현대카드X'] },
  { id: 'h-04', company: 'Hyundai', name: '현대카드 X BOOST', color: 'blue', gradient: 'bg-gradient-to-br from-indigo-600 via-blue-600 to-sky-700', image: '/cards/hyundaixboost.png', aliases: ['X BOOST'] },
  { id: 'h-05', company: 'Hyundai', name: '현대카드 ZERO Edition2 (할인형)', color: 'blue', gradient: 'bg-gradient-to-br from-sky-600 via-blue-500 to-indigo-700', image: '/cards/hyundaizerodiscount.png', aliases: ['ZERO Edition2 (할인형)', 'ZERO Edition3 (할인형)'] },
  { id: 'h-06', company: 'Hyundai', name: '현대카드 ZERO Edition2 (포인트형)', color: 'blue', gradient: 'bg-gradient-to-br from-blue-700 via-violet-600 to-indigo-800', image: '/cards/hyundaizeropoint.png', aliases: ['ZERO Edition2 (포인트형)', 'ZERO Edition3 (포인트형)', '현대카드ZERO Edition3(포인트형)'] },
  { id: 'h-07', company: 'Hyundai', name: '현대카드 Z family', color: 'blue', gradient: 'bg-gradient-to-br from-cyan-600 via-sky-600 to-indigo-700', image: '/cards/hyundaizfamily.png', aliases: ['현대카드Z family', 'Z family Edition2'] },
  { id: 'h-08', company: 'Hyundai', name: '현대카드 T3', color: 'blue', gradient: 'bg-gradient-to-br from-indigo-700 via-blue-600 to-slate-700', image: '/cards/hyundait3.png', aliases: ['현대카드 T3 Edition2'] },
  { id: 'h-09', company: 'Hyundai', name: '현대카드 Digital Lover', color: 'blue', gradient: 'bg-gradient-to-br from-blue-700 via-violet-600 to-indigo-800', image: '/cards/hyundaidigitallover.png', aliases: ['현대카드 DIGITAL LOVER'] },
  { id: 'h-10', company: 'Hyundai', name: '현대카드 Summit', color: 'blue', gradient: 'bg-gradient-to-br from-blue-800 via-indigo-800 to-slate-900', image: '/cards/hyundaisummit.png', aliases: ['Summit'] },
];

interface CardCarouselProps {
  isSpinning: boolean;
  highlightedCardId: string | null;
}

const CardCarousel: React.FC<CardCarouselProps> = ({ isSpinning, highlightedCardId }) => {
  const controls = useAnimation();
  const rotation = useMotionValue(0);
  const containerRef = useRef<HTMLDivElement>(null);
  
  const numCards = CARDS.length;
  const anglePerCard = 360 / numCards;
  const radius = 350;

  useEffect(() => {
    if (isSpinning) {
      controls.start({
        rotateY: [rotation.get(), rotation.get() - 360],
        transition: {
          duration: 2,
          ease: "linear",
          repeat: Infinity,
        }
      });
    } else if (highlightedCardId) {
      const targetIndex = CARDS.findIndex(c => c.id === highlightedCardId);
      
      if (targetIndex !== -1) {
        let currentRotation = rotation.get();
        const normalizedCurrent = currentRotation % 360;
        
        const targetRotation = -targetIndex * anglePerCard;
        
        let delta = targetRotation - normalizedCurrent;
        
        if (delta > 180) delta -= 360;
        if (delta < -180) delta += 360;
        
        const finalRotation = currentRotation + delta;

        controls.start({
          rotateY: finalRotation,
          transition: {
            duration: 1.2,
            type: "spring",
            stiffness: 40,
            damping: 10
          }
        });
      }
    } else {
        controls.stop();
    }
  }, [isSpinning, highlightedCardId, anglePerCard, controls, rotation]);

  const handleUpdate = (latest: any) => {
      if (typeof latest.rotateY === 'number') {
          rotation.set(latest.rotateY);
      }
  };

  return (
    <div className="w-full h-full flex items-center justify-center overflow-hidden" style={{ perspective: '1200px' }}>
      <motion.div
        ref={containerRef}
        className="relative w-[220px] h-[340px]"
        style={{ 
          transformStyle: 'preserve-3d',
          rotateY: rotation
        }}
        animate={controls}
        onUpdate={handleUpdate}
      >
        {CARDS.map((card, index) => {
          const cardAngle = index * anglePerCard;
          
          return (
            <div
              key={card.id}
              className={`absolute top-0 left-0 w-full h-full rounded-2xl shadow-2xl p-6 flex flex-col justify-between text-white border border-white/20 backdrop-blur-md overflow-hidden ${card.gradient}`}
              style={{
                transform: `rotateY(${cardAngle}deg) translateZ(${radius}px)`,
                backfaceVisibility: 'visible',
              }}
            >
              <div className="absolute inset-0 pointer-events-none">
                <Image
                  src={card.image || FALLBACK_CARD_IMAGE}
                  alt={card.name}
                  fill
                  sizes="220px"
                  className="object-cover opacity-45 mix-blend-screen"
                />
              </div>

              <div className="absolute inset-0 bg-gradient-to-b from-black/25 via-transparent to-black/55 pointer-events-none" />

              <div className="flex justify-between items-start">
                <div className="text-sm font-semibold tracking-wider opacity-90 uppercase">{card.company}</div>
                <div className="w-8 h-8 rounded-full bg-white/20 backdrop-blur-sm border border-white/10" />
              </div>
               
              <div className="space-y-4">
                <div className="w-full h-[96px] rounded-lg bg-black/25 border border-white/15 p-2 flex items-center justify-center overflow-hidden">
                  <Image
                    src={card.image || FALLBACK_CARD_IMAGE}
                    alt={card.name}
                    width={220}
                    height={96}
                    className="w-full h-full object-contain"
                  />
                </div>
                <div className="text-lg font-bold tracking-tight drop-shadow-lg leading-tight line-clamp-3">{card.name}</div>
              </div>
              
              <div className="flex justify-between items-end opacity-90 mt-4">
                <div className="text-xs font-mono tracking-widest">**** 1234</div>
                <div className="text-[10px] font-semibold">VALID 12/28</div>
              </div>

              <div className="absolute inset-0 rounded-2xl bg-gradient-to-tr from-white/0 via-white/10 to-white/0 pointer-events-none" />
              <div className="absolute -inset-[1px] rounded-2xl border border-white/20 pointer-events-none" />
            </div>
          );
        })}
      </motion.div>
      
      <div 
        className="absolute bottom-[-100px] w-[600px] h-[600px] bg-black/20 rounded-full blur-[80px] pointer-events-none"
        style={{
            transform: 'rotateX(90deg) translateZ(-200px) scale(0.8)'
        }}
       />
    </div>
  );
};

export default CardCarousel;
