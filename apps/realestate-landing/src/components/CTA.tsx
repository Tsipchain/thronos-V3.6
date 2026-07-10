'use client';

export function CTA() {
  return (
    <section className="py-20 px-4 bg-blue-600 text-white">
      <div className="max-w-4xl mx-auto text-center">
        <h2 className="text-4xl font-bold mb-6">Ready to Own Greek Real Estate?</h2>
        <p className="text-xl mb-8 opacity-95">
          Join 50+ international investors earning 5-8% annual yields on blockchain-verified properties
        </p>
        <button className="px-8 py-4 bg-white text-blue-600 rounded-lg hover:bg-gray-100 font-bold text-lg">
          Start Investor Onboarding
        </button>
        <p className="mt-6 text-sm opacity-75">KYC takes 5 minutes • No hidden fees • Fully compliant</p>
      </div>
    </section>
  );
}
