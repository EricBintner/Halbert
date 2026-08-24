import React, { useState } from 'react';

export function CouponBox() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('idle');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!email || !email.includes('@')) return;
    setStatus('submitting');
    setTimeout(() => {
      setStatus('success');
    }, 500);
  };

  return (
    <div className="w-full dashed-coupon p-6 sm:p-8 space-y-4 text-white font-serif">
      {/* Scissor Cut Line Header */}
      <div className="flex items-center justify-between text-xs font-mono text-white/70 border-b border-dashed border-white/40 pb-2">
        <span className="flex items-center space-x-1">
          <span>✂</span>
          <span>CUT ALONG DOTTED LINE TO RECEIVE TECHNICAL PROSPECTUS</span>
        </span>
        <span className="hidden sm:inline font-bold text-white">NO POSTAGE REQUIRED</span>
      </div>

      {status === 'success' ? (
        <div className="p-6 text-center space-y-2 bg-[#152E6F]/60 border border-white/40">
          <div className="font-display font-bold text-xl text-white">
            Prospectus Inquiry Registered.
          </div>
          <p className="text-xs font-serif text-white/80 max-w-md mx-auto">
            Your name and dispatch address have been inscribed upon the Halbert Early Registry. Technical release notes and binaries will be dispatched upon publication.
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <div className="font-display font-bold text-sm tracking-wide uppercase text-white">
              Halbert Computing Apparatus Corporation
            </div>
            <div className="text-[11px] font-mono text-white/70">
              Department of Local Intelligence · Box 402 · Palo Alto, California
            </div>
          </div>

          <div className="text-xs font-serif text-white/90 leading-relaxed">
            Gentlemen: Please enroll my name upon the roster for the Halbert Host Intelligence System. I understand that all software executes 100% locally upon my machine without subscription fees or cloud intrusion.
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs font-mono">
            <div>
              <label className="block text-[10px] uppercase text-white/60 mb-1">
                Your Full Name:
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., Dr. Arthur C. Clarke"
                className="w-full px-3 py-2 bg-[#152E6F]/70 border border-white/40 text-white placeholder-white/40 text-xs focus:outline-none focus:border-white font-serif"
                required
              />
            </div>

            <div>
              <label className="block text-[10px] uppercase text-white/60 mb-1">
                Your Email Address:
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="e.g., arthur@clarke.org"
                className="w-full px-3 py-2 bg-[#152E6F]/70 border border-white/40 text-white placeholder-white/40 text-xs focus:outline-none focus:border-white font-serif"
                required
              />
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-2 border-t border-dashed border-white/40">
            <div className="text-[10.5px] font-mono text-white/70">
              [✓] macOS &amp; Linux Compatible · Free &amp; Open Source
            </div>
            <button
              type="submit"
              disabled={status === 'submitting'}
              className="w-full sm:w-auto px-6 py-2.5 bg-white text-[#1E40AF] font-display font-black text-xs uppercase tracking-wider hover:bg-[#F8FAFC] transition-colors border border-white shrink-0 cursor-pointer"
            >
              {status === 'submitting' ? 'Transmitting…' : 'Mail Coupon →'}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
