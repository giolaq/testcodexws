import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { headers } from "next/headers";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const socialImages = process.env.VERCEL === "1"
    ? []
    : [{ url: "/og.png", width: 1731, height: 909, alt: "Software (re)-Factory self-guided workshop" }];

  return {
    metadataBase: new URL(`${protocol}://${host}`),
    title: "Software (re)-Factory Workshop",
    description:
      "A self-guided developer workshop for understanding, designing, and operating an AI software factory.",
    openGraph: {
      title: "Software (re)-Factory Workshop",
      description:
        "Learn why AI software factories matter, trace one PRD from intent to evidence, and design the right controls for your team.",
      type: "website",
      images: socialImages,
    },
    twitter: {
      card: "summary_large_image",
      title: "Software (re)-Factory Workshop",
      description: "Turn AI coding into an engineering system with planning, QA, isolation, evidence, and human control.",
      images: socialImages.map((image) => image.url),
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
