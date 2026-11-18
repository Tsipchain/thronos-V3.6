'use client';

export function Testimonials() {
  const testimonials = [
    {
      name: 'Alexander K.',
      country: 'Switzerland',
      text: 'Completed KYC in 5 minutes. Now earning €2,300/month from 2 properties. Best Web3 investment I\'ve made.'
    },
    {
      name: 'Maria S.',
      country: 'Singapore',
      text: 'As an international investor, the legal compliance piece was always the hardest. THRONOS made it effortless.'
    },
    {
      name: 'David T.',
      country: 'USA',
      text: 'Smart contracts handle everything. I don\'t have to worry about transfer fees or delays. Completely transparent.'
    }
  ];

  return (
    <section id="testimonials" className="py-20 px-4 bg-gray-50">
      <div className="max-w-6xl mx-auto">
        <h2 className="text-4xl font-bold text-gray-900 mb-12 text-center">What Investors Say</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {testimonials.map((test, idx) => (
            <div key={idx} className="bg-white rounded-xl p-8 shadow-md">
              <div className="flex mb-4">
                {[...Array(5)].map((_, i) => (
                  <span key={i} className="text-yellow-400 text-lg">★</span>
                ))}
              </div>
              <p className="text-gray-700 mb-6 italic">"{test.text}"</p>
              <div>
                <p className="font-bold text-gray-900">{test.name}</p>
                <p className="text-sm text-gray-600">{test.country}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
