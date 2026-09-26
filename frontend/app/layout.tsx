import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NoveltyLens — Review Novelty & Relevance Scoring",
  description: "Evaluate product review novelty and relevance using local vector embeddings, cosine similarity, and OpenRouter LLM judges.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#0b0f19] text-slate-100 antialiased selection:bg-indigo-500 selection:text-white min-h-screen flex flex-col">
        {children}
      </body>
    </html>
  );
}
