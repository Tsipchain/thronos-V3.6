'use client';

export function ThreePillars() {
  const pillars = [
    {
      icon: '🔐',
      title: 'Verified Digital Identity & Compliance',
      description: 'Skip the bureaucracy. Through VerifyID, international investors undergo instant, secure KYC/AML compliance. Get your Web3 hosting, encrypted corporate communication, and decentralized ID in minutes.'
    },
    {
      icon: '🏢',
      title: 'Physical & Legal Corporate Substance',
      description: 'Establish a legitimate legal and tax footprint in Greece. We provide premium virtual/physical office address services, ensuring your business fully complies with EU regulations while enjoying local strategic advantages.'
    },
    {
      icon: '🏡',
      title: 'High-Yield Real Estate Portfolio',
      description: 'Gain exclusive access to a curated portfolio of 200+ premium properties in the high-growth tourist zones of Ouranoupoli and Nea Roda. Managed efficiently, optimized for high rental yields, and ready for Web3 integration.'
    }
  ];

  return (
    <section id="pillars" className="py-20 px-4 bg-white">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-4xl font-bold text-gray-900 mb-4">
            The All-in-One Investor Package
          </h2>
          <p className="text-xl text-gray-600">Three Integrated Pillars for Global Investors</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {pillars.map((pillar, idx) => (
            <div key={idx} className="bg-gradient-to-br from-blue-50 to-white rounded-xl p-8 border border-gray-200 hover:shadow-lg transition-shadow">
              <div className="text-5xl mb-4">{pillar.icon}</div>
              <h3 className="text-xl font-bold text-gray-900 mb-3">{pillar.title}</h3>
              <p className="text-gray-700 leading-relaxed">{pillar.description}</p>
            </div>
          ))}
        </div>

        <div className="mt-16 bg-blue-600 rounded-xl p-12 text-white text-center">
          <h3 className="text-3xl font-bold mb-4">Complete Package Price</h3>
          <p className="text-2xl mb-6">€2,500 - €5,000 setup + €250-€400/month</p>
          <p className="text-lg opacity-90">Own premium Greek real estate. Verified. Legal. Profitable.</p>
        </div>
      </div>
    </section>
  );
}
