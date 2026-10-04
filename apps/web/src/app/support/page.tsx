import { JsonLd } from '@/components/legal/json-ld';
import { RichText } from '@/components/legal/rich-text';
import { SupportForm } from '@/components/legal/support-form';
import { GlassPanel } from '@/components/ui/glass-panel';
import { legalMetadata, webPageJsonLd } from '@/lib/legal-seo';
import { breadcrumbJsonLd } from '@/lib/seo';
import { legalMessages } from '@/messages/legal';

const { support } = legalMessages();
const SEO = { path: '/support', title: support.title, description: support.description } as const;

export const metadata = legalMetadata(SEO);

export default function SupportPage() {
  return (
    <div className="mx-auto w-full max-w-[46rem] px-4 pt-[max(28px,env(safe-area-inset-top))] pb-8 tablet:px-6">
      <JsonLd data={webPageJsonLd(SEO)} />
      <JsonLd data={breadcrumbJsonLd([{ name: SEO.title, path: SEO.path }])} />
      <GlassPanel
        as="article"
        ornate
        className="motion-safe:animate-fade-in flex flex-col gap-5 p-5 tablet:p-8"
      >
        <header className="flex flex-col gap-3">
          <h1 className="m-0 font-bold text-[2rem] text-gilded tablet:text-[2.5rem]">
            {support.title}
          </h1>
          <p className="m-0 text-fg leading-[2]">{support.intro}</p>
          <p className="m-0 text-fg-soft leading-[2]">
            {support.privacyNote} <RichText text={support.privacyEmail} />.
          </p>
          <p className="m-0 text-fg-soft text-sm leading-[2]">{support.noStorage}</p>
        </header>
        <SupportForm />
      </GlassPanel>
    </div>
  );
}
