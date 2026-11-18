import { Hero } from '@/components/Hero';
import { ThreePillars } from '@/components/ThreePillars';
import { PropertyShowcase } from '@/components/PropertyShowcase';
import { InvestorCalculator } from '@/components/InvestorCalculator';
import { Testimonials } from '@/components/Testimonials';
import { CTA } from '@/components/CTA';
import { Footer } from '@/components/Footer';
import { Navigation } from '@/components/Navigation';

export default function Home() {
  return (
    <>
      <Navigation />
      <Hero />
      <ThreePillars />
      <PropertyShowcase />
      <InvestorCalculator />
      <Testimonials />
      <CTA />
      <Footer />
    </>
  );
}
