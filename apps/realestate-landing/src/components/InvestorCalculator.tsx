'use client';

import { useState } from 'react';

export function InvestorCalculator() {
  const [investment, setInvestment] = useState(50000);

  const annualYield = investment * 0.065; // 6.5% baseline
  const monthlyYield = annualYield / 12;
  const setupFee = 2500;

  return (
    <section id="calculator" className="py-20 px-4 bg-white">
      <div className="max-w-4xl mx-auto">
        <h2 className="text-4xl font-bold text-gray-900 mb-4 text-center">
          How Much Can You Earn?
        </h2>
        <p className="text-center text-gray-600 mb-12 text-lg">
          Interactive calculator showing your potential returns
        </p>

        <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-2xl p-12">
          <div className="mb-8">
            <label className="block text-gray-900 font-semibold mb-4">
              Investment Amount: €{investment.toLocaleString()}
            </label>
            <input
              type="range"
              min="10000"
              max="1000000"
              value={investment}
              onChange={(e) => setInvestment(Number(e.target.value))}
              className="w-full h-2 bg-blue-300 rounded-lg appearance-none cursor-pointer"
            />
            <div className="flex justify-between text-sm text-gray-600 mt-2">
              <span>€10K</span>
              <span>€1M</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="bg-white rounded-xl p-6">
              <p className="text-gray-600 text-sm font-medium mb-2">Setup & First Year</p>
              <p className="text-4xl font-bold text-blue-600 mb-2">
                €{(setupFee + monthlyYield * 12).toLocaleString()}
              </p>
              <p className="text-gray-700 text-sm">
                Includes €{setupFee.toLocaleString()} setup + €{(monthlyYield * 12).toLocaleString()} yield
              </p>
            </div>

            <div className="bg-white rounded-xl p-6">
              <p className="text-gray-600 text-sm font-medium mb-2">Monthly Passive Income</p>
              <p className="text-4xl font-bold text-green-600 mb-2">
                €{monthlyYield.toLocaleString('en-US', { maximumFractionDigits: 0 })}
              </p>
              <p className="text-gray-700 text-sm">
                Automated via smart contracts to your wallet
              </p>
            </div>
          </div>

          <div className="mt-8 p-6 bg-white rounded-xl border-l-4 border-blue-600">
            <p className="text-gray-700">
              <span className="font-bold text-gray-900">Why invest with THRONOS?</span><br />
              Your property is blockchain-verified, fully compliant with EU regulations, and your yields are automated through smart contracts. No hidden fees. No bureaucracy.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
