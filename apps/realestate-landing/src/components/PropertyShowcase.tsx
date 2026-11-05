'use client';

export function PropertyShowcase() {
  const properties = [
    { name: 'Villa Petra', location: 'Ouranoupoli', yield: '6.5%', price: '€450K' },
    { name: 'Seaside Boutique', location: 'Nea Roda', yield: '7.2%', price: '€520K' },
    { name: 'Garden Estate', location: 'Ouranoupoli', yield: '5.8%', price: '€380K' }
  ];

  return (
    <section id="portfolio" className="py-20 px-4 bg-gray-50">
      <div className="max-w-6xl mx-auto">
        <h2 className="text-4xl font-bold text-gray-900 mb-12 text-center">Featured Properties</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {properties.map((prop, idx) => (
            <div key={idx} className="bg-white rounded-xl overflow-hidden shadow-md hover:shadow-xl transition-shadow">
              <div className="bg-gradient-to-br from-blue-400 to-blue-600 h-48"></div>
              <div className="p-6">
                <h3 className="text-xl font-bold text-gray-900 mb-2">{prop.name}</h3>
                <p className="text-gray-600 mb-4">{prop.location}</p>
                <div className="flex justify-between items-center">
                  <span className="text-2xl font-bold text-blue-600">{prop.yield}</span>
                  <span className="text-gray-700 font-semibold">{prop.price}</span>
                </div>
                <button className="w-full mt-4 px-4 py-2 bg-blue-100 text-blue-600 rounded-lg hover:bg-blue-200 font-semibold">
                  View Details
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
