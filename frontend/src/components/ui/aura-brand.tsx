export function AuraMark({ size = 22 }: { size?: number }) {
  return (
    <span
      className="inline-block rounded-full"
      style={{
        width: size,
        height: size,
        background:
          "radial-gradient(circle at 35% 30%, rgba(255,255,255,0.65), transparent 50%), radial-gradient(circle at 50% 50%, #818cf8, #6366f1 45%, #4338ca 75%, #0a0a12 100%)",
        boxShadow: "0 0 0 1px rgba(255,255,255,0.08), 0 0 16px rgba(99,102,241,0.55)",
      }}
    />
  );
}

export function AuraOrb({ className = "" }: { className?: string }) {
  return (
    <div className={`relative aspect-square ${className}`}>
      {/* Glow */}
      <div className="absolute -inset-[10%] rounded-full animate-pulse-glow" style={{
        background: "radial-gradient(closest-side, rgba(99,102,241,0.45), transparent 70%)",
        filter: "blur(24px)",
      }} />
      {/* Rings */}
      {[0, 1.4, 2.8, 4.2].map((delay, i) => (
        <div key={i} className="absolute inset-0 rounded-full animate-ring-expand" style={{
          border: "1px solid rgba(99,102,241,0.20)",
          animationDelay: `${delay}s`,
        }} />
      ))}
      {/* Core */}
      <div className="absolute inset-[18%] rounded-full animate-breathe overflow-hidden z-[2]" style={{
        background: "radial-gradient(circle at 32% 28%, rgba(255,255,255,0.85) 0%, rgba(255,255,255,0.18) 12%, transparent 26%), radial-gradient(circle at 50% 50%, #a5b4fc 0%, #818cf8 18%, #6366f1 38%, #4338ca 62%, #1e1b4b 86%, #0a0a12 100%)",
        boxShadow: "inset 0 0 40px rgba(99,102,241,0.6), inset 0 -30px 60px rgba(10,10,18,0.7), 0 0 80px rgba(99,102,241,0.55), 0 0 0 1px rgba(255,255,255,0.08)",
      }}>
        {/* Swirl overlay */}
        <div className="absolute inset-0 animate-swirl" style={{
          background: "conic-gradient(from 0deg, rgba(255,255,255,0) 0deg, rgba(255,255,255,0.18) 60deg, rgba(99,102,241,0) 140deg, rgba(255,255,255,0.10) 220deg, rgba(99,102,241,0) 300deg, rgba(255,255,255,0) 360deg)",
          mixBlendMode: "screen",
          filter: "blur(8px)",
        }} />
        {/* Specular highlight */}
        <div className="absolute top-[6%] left-[14%] w-[36%] h-[22%] rounded-full" style={{
          background: "radial-gradient(closest-side, rgba(255,255,255,0.6), transparent 70%)",
          filter: "blur(6px)",
        }} />
      </div>
    </div>
  );
}
