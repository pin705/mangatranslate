import { LanguageSwitcher } from "@/components/language-switcher";
import { Logo } from "@/components/logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4">
        <Logo />
        <LanguageSwitcher />
      </header>
      <main id="main" className="flex flex-1 items-start justify-center px-4 py-10">
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </>
  );
}
