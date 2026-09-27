import { RegisterForm } from "@/components/auth-forms";
import { pageMetadata } from "@/lib/seo";

export const generateMetadata = () => pageMetadata("register", "/register");

export default function Page() {
  return <RegisterForm />;
}
