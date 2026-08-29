'use client';

export function Hero() {
  return (
    <section className="pt-32 pb-20 px-4 bg-gradient-to-b from-blue-50 to-white">
      <div className="max-w-4xl mx-auto text-center">
        <h1 className="text-5xl md:text-6xl font-bold text-gray-900 mb-6 leading-tight">
          The Future of Real Estate<br />
          <span className="text-blue-600">Managed on the Blockchain</span>
        </h1>

        <p className="text-xl text-gray-600 mb-8 max-w-2xl mx-auto leading-relaxed">
          Establish your corporate presence, secure premium properties, and onboard seamlessly in the gateway of Mount Athos. Powered by Thronoschain.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-12">
          <button className="px-8 py-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-semibold text-lg w-full sm:w-auto">
            Explore Portfolio
          </button>
          <button className="px-8 py-4 border-2 border-blue-600 text-blue-600 rounded-lg hover:bg-blue-50 font-semibold text-lg w-full sm:w-auto">
            Start Investor Onboarding
          </button>
        </div>

        <div className="bg-white rounded-2xl p-12 border border-gray-200 shadow-lg">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="text-4xl font-bold text-blue-600 mb-2">5 min</div>
              <p className="text-gray-700">Complete KYC/AML<br />vs 6-8 weeks</p>
            </div>
            <div className="text-center">
              <div className="text-4xl font-bold text-blue-600 mb-2">200+</div>
              <p className="text-gray-700">Premium Properties<br />Verified on Blockchain</p>
            </div>
            <div className="text-center">
              <div className="text-4xl font-bold text-blue-600 mb-2">5-8%</div>
              <p className="text-gray-700">Annual Yield<br />Smart Contract Automated</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
