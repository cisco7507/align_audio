import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Align Audio Studio",
  description: "Align in-house and external audio using a FastAPI backend",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
