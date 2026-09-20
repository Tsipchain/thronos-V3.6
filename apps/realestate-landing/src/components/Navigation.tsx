'use client';

import Link from 'next/link';

export function Navigation() {
  return (
    <nav className="fixed top-0 w-full bg-white/80 backdrop-blur-md z-50 border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link href="/" className="flex items-center space-x-2">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-lg">⊕</span>
            </div>
            <span className="font-bold text-lg text-gray-900">THRONOS</span>
          </Link>

          <div className="hidden md:flex items-center space-x-8">
            <a href="#pillars" className="text-gray-700 hover:text-blue-600 text-sm font-medium">Services</a>
            <a href="#portfolio" className="text-gray-700 hover:text-blue-600 text-sm font-medium">Portfolio</a>
            <a href="#calculator" className="text-gray-700 hover:text-blue-600 text-sm font-medium">Calculator</a>
            <a href="#testimonials" className="text-gray-700 hover:text-blue-600 text-sm font-medium">Testimonials</a>
          </div>

          <div className="flex items-center space-x-4">
            <button className="hidden sm:block px-4 py-2 text-blue-600 border border-blue-600 rounded-lg hover:bg-blue-50 text-sm font-medium">
              Sign In
            </button>
            <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium">
              Start Investing
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
