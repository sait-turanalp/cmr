"use client";

import { signIn } from "next-auth/react";
import { useToast } from "@/hooks/use-toast";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function SignIn() {
  const { toast } = useToast();
  const router = useRouter();

  // Dashboard'u kullanici sifreyi yazarken arka planda cek — giris aninda
  // navigasyon bekleme suresi ~200ms yerine ~0 olur.
  useEffect(() => {
    router.prefetch("/dashboard");
  }, [router]);

  const handleSignIn = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const email = event.currentTarget.username.value;
    const password = event.currentTarget.password.value;

    try {
      const response = await signIn("credentials", {
        email,
        password,
        redirect: false,
      });

      if (response?.error) {
        toast({
          title: "Giriş Yapılamadı",
          description: "Bilgilerinizi kontrol ediniz. Tekrar deneyiniz.",
          variant: "destructive",
        });
      } else {
        // Once yonlendir, toast'i sonra goster — toast render'i navigasyonu
        // bekletmesin.
        router.push("/dashboard");
        toast({
          title: "Giriş Yapıldı",
          description: "Giriş başarılı. Yönlendiriliyorsunuz...",
          variant: "default",
        });
      }
    } catch (error: any) {
      console.error("Login Error:", error);
      // Check for Server Action mismatch error
      if (
        error.message?.includes("Failed to find Server Action") ||
        error.message?.includes("fetch failed")
      ) {
        toast({
          title: "Sürüm Güncellendi",
          description: "Sayfa yenileniyor, lütfen tekrar giriş yapın.",
          variant: "default",
        });
        // Short delay to let the toast appear
        setTimeout(() => {
          window.location.reload();
        }, 1000);
      } else {
        toast({
          title: "Hata",
          description: "Beklenmedik bir hata oluştu.",
          variant: "destructive",
        });
      }
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            Panele Giriş Yap
          </h2>
        </div>
        <form className="mt-8 space-y-6" onSubmit={handleSignIn}>
          <div className="rounded-md shadow-sm -space-y-px">
            <div>
              <label htmlFor="username" className="sr-only">
                Kullanıcı Adı
              </label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-t-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm"
                placeholder="Kullanıcı Adı"
              />
            </div>
            <div>
              <label htmlFor="password" className="sr-only">
                Şifre
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-b-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm"
                placeholder="Şifre"
              />
            </div>
          </div>
          <div>
            <button
              type="submit"
              className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
            >
              Giriş Yap
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
