import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono, Instrument_Sans } from "next/font/google";
import "./globals.css";
import Rack from "@/components/Rack";

const archivo = Archivo({
  variable: "--archivo",
  subsets: ["latin"],
  weight: ["700", "800"],
});

const instrument = Instrument_Sans({
  variable: "--instrument",
  subsets: ["latin"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Tembr",
  description: "Local, private voice cloning studio",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${archivo.variable} ${instrument.variable} ${plexMono.variable}`}
    >
      <body>
        <div className="shell">
          <Rack />
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
