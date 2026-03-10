import React, { useEffect, useRef } from 'react';
import Image from 'next/image';
import { Swiper, SwiperSlide } from 'swiper/react';
import { EffectCoverflow, Pagination, Autoplay, Navigation } from 'swiper/modules';
import type { Swiper as SwiperType } from 'swiper';

// Import Swiper styles
import 'swiper/css';
import 'swiper/css/effect-coverflow';
import 'swiper/css/pagination';
import 'swiper/css/navigation';

export interface OrbitItem {
  id: string;
  eyebrow: string; // Company name
  title: string;   // Card name
  description: string;
  meta: string;    // "Credit Card"
  image: string;
}

interface SwiperCarouselProps {
  items: OrbitItem[];
  activeId: string | null;
  onChange?: (id: string) => void;
  orbitSpeed?: number; // mapped to autoplay speed
  radius?: number; // unused in swiper but kept for compat
  className?: string;
}

const SwiperCarousel: React.FC<SwiperCarouselProps> = ({
  items,
  activeId,
  onChange,
  orbitSpeed = 0.1,
  className,
}) => {
  const swiperRef = useRef<SwiperType | null>(null);

  // Map orbitSpeed to autoplay delay (inverse relationship: higher speed = lower delay)
  // Base delay: 3000ms. Speed 0.1 -> 3000ms. Speed 2 -> 500ms?
  // Let's say speed 1 = 1000ms.
  // speed 0.1 is very slow. Maybe disable autoplay if too slow?
  // For now, let's just use a reasonable default if speed is provided.
  const autoplayDelay = orbitSpeed > 1 ? 1000 : 3000;
  const isSpinning = orbitSpeed > 1;

  useEffect(() => {
    if (swiperRef.current && activeId) {
      const index = items.findIndex((item) => item.id === activeId);
      if (index >= 0 && swiperRef.current.activeIndex !== index) {
        swiperRef.current.slideToLoop(index);
      }
    }
  }, [activeId, items]);

  return (
    <div className={`swiper-carousel-container ${className || ''} h-full w-full flex items-center justify-center`}>
      <Swiper
        effect={'coverflow'}
        grabCursor={true}
        centeredSlides={true}
        slidesPerView={'auto'}
        coverflowEffect={{
          rotate: 50,
          stretch: 0,
          depth: 100,
          modifier: 1,
          slideShadows: true,
        }}
        pagination={false}
        navigation={true}
        modules={[EffectCoverflow, Pagination, Autoplay, Navigation]}
        className="mySwiper w-full h-full max-w-4xl py-10"
        loop={true}
        autoplay={
          isSpinning
            ? {
                delay: 500,
                disableOnInteraction: false,
              }
            : false
        }
        onSwiper={(swiper) => {
          swiperRef.current = swiper;
        }}
        onSlideChange={(swiper) => {
          if (onChange) {
            const index = swiper.realIndex;
            const item = items[index];
            if (item) {
              onChange(item.id);
            }
          }
        }}
      >
        {items.map((item) => (
          <SwiperSlide
            key={item.id}
            className="w-[280px] h-[400px] bg-white/5 backdrop-blur-md rounded-2xl border border-white/10 p-6 flex flex-col shadow-xl transition-all duration-300 overflow-hidden relative"
            style={{ width: '280px', height: '400px' }} // Explicit size for coverflow
          >
            <div className="absolute inset-0 pointer-events-none">
              <Image
                src={item.image}
                alt={item.title}
                fill
                sizes="280px"
                className="object-cover opacity-50 mix-blend-screen"
              />
            </div>

            <div className="absolute inset-0 bg-gradient-to-b from-black/35 via-transparent to-black/60 pointer-events-none" />

            <div className="flex-1 flex flex-col gap-4">
              <span className="text-xs uppercase tracking-widest text-white/60 font-semibold">
                {item.eyebrow}
              </span>
              <div className="relative w-full h-[120px] rounded-xl bg-black/25 border border-white/15 p-2 overflow-hidden">
                <Image
                  src={item.image}
                  alt={item.title}
                  fill
                  sizes="240px"
                  className="object-contain"
                />
              </div>
              <h3 className="text-2xl font-bold text-white drop-shadow-md">
                {item.title}
              </h3>
              <p className="text-sm text-white/70 leading-relaxed">
                {item.description}
              </p>
            </div>
            <div className="mt-auto flex items-center justify-between border-t border-white/10 pt-4">
              <span className="px-3 py-1 rounded-full bg-customTeal/20 text-customTeal text-[10px] font-bold uppercase tracking-wider border border-customTeal/30">
                {item.meta}
              </span>
              <span className="text-customTeal text-xs font-bold uppercase tracking-widest">
                View
              </span>
            </div>
            
            {/* Glossy effects */}
            <div className="absolute inset-0 bg-gradient-to-br from-white/10 via-transparent to-transparent pointer-events-none rounded-2xl" />
          </SwiperSlide>
        ))}
      </Swiper>
      <style jsx global>{`
        .swiper-slide-shadow-left,
        .swiper-slide-shadow-right {
          background-image: none !important;
          background-color: rgba(0, 0, 0, 0.5) !important;
          border-radius: 1rem;
        }
        .swiper-button-next,
        .swiper-button-prev {
          color: #4ac0a7 !important;
          text-shadow: 0 0 10px rgba(74, 192, 167, 0.5);
          transition: all 0.3s ease;
        }
        .swiper-button-next:hover,
        .swiper-button-prev:hover {
          color: #fff !important;
          transform: scale(1.1);
          text-shadow: 0 0 20px rgba(74, 192, 167, 0.8);
        }
        .swiper-button-next::after,
        .swiper-button-prev::after {
          font-size: 2rem !important;
          font-weight: bold;
        }
      `}</style>
    </div>
  );
};

export default SwiperCarousel;
