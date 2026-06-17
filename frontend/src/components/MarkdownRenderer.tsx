"use client";

import React, { useState } from "react";
import { Check, Copy, Terminal } from "lucide-react";

interface MarkdownRendererProps {
  content: string;
  isStreaming?: boolean;
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content, isStreaming = false }) => {
  // Renders inline formatting like bold (**text**) and code (`text`)
  const parseInline = (text: string): React.ReactNode[] => {
    if (!text) return [];

    const parts: React.ReactNode[] = [];
    let currentText = text;
    let index = 0;

    while (currentText.length > 0) {
      // Find nearest bold or code match
      const boldIdx = currentText.indexOf("**");
      const codeIdx = currentText.indexOf("`");

      // No matches left
      if (boldIdx === -1 && codeIdx === -1) {
        parts.push(<span key={`txt-${index}`}>{currentText}</span>);
        break;
      }

      // Check which delimiter comes first
      if (boldIdx !== -1 && (codeIdx === -1 || boldIdx < codeIdx)) {
        // Text before bold
        if (boldIdx > 0) {
          parts.push(<span key={`txt-${index}`}>{currentText.substring(0, boldIdx)}</span>);
          currentText = currentText.substring(boldIdx);
        }

        // Find closing bold
        const closeBoldIdx = currentText.indexOf("**", 2);
        if (closeBoldIdx !== -1) {
          const boldText = currentText.substring(2, closeBoldIdx);
          parts.push(<strong key={`bold-${index}`} className="font-bold text-slate-900">{boldText}</strong>);
          currentText = currentText.substring(closeBoldIdx + 2);
        } else {
          // Unclosed bold (during streaming)
          parts.push(<strong key={`bold-${index}`} className="font-bold text-slate-900">{currentText.substring(2)}</strong>);
          break;
        }
      } else {
        // Inline code first
        if (codeIdx > 0) {
          parts.push(<span key={`txt-${index}`}>{currentText.substring(0, codeIdx)}</span>);
          currentText = currentText.substring(codeIdx);
        }

        // Find closing code tick
        const closeCodeIdx = currentText.indexOf("`", 1);
        if (closeCodeIdx !== -1) {
          const codeText = currentText.substring(1, closeCodeIdx);
          parts.push(
            <code key={`code-${index}`} className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 text-teal-700 font-mono text-xs">
              {codeText}
            </code>
          );
          currentText = currentText.substring(closeCodeIdx + 1);
        } else {
          // Unclosed inline code
          parts.push(
            <code key={`code-${index}`} className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 text-teal-700 font-mono text-xs">
              {currentText.substring(1)}
            </code>
          );
          break;
        }
      }
      index++;
    }

    return parts;
  };

  // Internal component for code blocks with copy-to-clipboard support
  const CodeBlockComponent = ({ code, language }: { code: string; language: string }) => {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
      try {
        await navigator.clipboard.writeText(code);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch (err) {
        console.error("Failed to copy code", err);
      }
    };

    return (
      <div className="relative border border-slate-800 rounded-xl overflow-hidden my-4 group shadow-md bg-slate-950">
        <div className="flex justify-between items-center px-4 py-2 bg-slate-900/80 border-b border-slate-800 text-slate-400 text-xs font-semibold">
          <span className="flex items-center gap-1.5 font-mono">
            <Terminal className="h-3.5 w-3.5 text-teal-500" />
            {language || "code"}
          </span>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 hover:text-white transition p-1 bg-slate-800 hover:bg-slate-700 rounded-lg"
            title="Copy to clipboard"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
            <span>{copied ? "Copied" : "Copy"}</span>
          </button>
        </div>
        <pre className="p-4 overflow-x-auto text-xs md:text-sm font-mono leading-relaxed bg-slate-950 text-slate-200 select-all">
          <code>{code}</code>
        </pre>
      </div>
    );
  };

  // Convert raw text into structured React nodes line-by-line
  const renderContent = () => {
    const lines = content.split("\n");
    const elements: React.ReactNode[] = [];
    
    let inCodeBlock = false;
    let codeLanguage = "";
    let codeContent: string[] = [];
    let listItems: string[] = [];
    let isListActive = false;

    const flushList = (key: number) => {
      if (listItems.length > 0) {
        elements.push(
          <ul key={`ul-${key}`} className="list-disc pl-5 my-3 space-y-1.5 text-slate-700 text-sm">
            {listItems.map((item, idx) => (
              <li key={idx} className="leading-relaxed">{parseInline(item)}</li>
            ))}
          </ul>
        );
        listItems = [];
        isListActive = false;
      }
    };

    lines.forEach((line, index) => {
      // Check for Code Block boundaries
      if (line.trim().startsWith("```")) {
        if (inCodeBlock) {
          // End of code block
          elements.push(
            <CodeBlockComponent
              key={`code-${index}`}
              code={codeContent.join("\n")}
              language={codeLanguage}
            />
          );
          inCodeBlock = false;
          codeContent = [];
          codeLanguage = "";
        } else {
          // Start of list must be flushed
          flushList(index);
          
          // Start of code block
          inCodeBlock = true;
          codeLanguage = line.trim().slice(3).trim();
        }
        return;
      }

      // If we are currently inside a code block, gather lines
      if (inCodeBlock) {
        codeContent.push(line);
        return;
      }

      // Check for headers (e.g. # Title, ## Subtitle)
      const headerMatch = line.match(/^(#{1,6})\s+(.+)$/);
      if (headerMatch) {
        flushList(index);
        const depth = headerMatch[1].length;
        const text = headerMatch[2];

        if (depth === 1) {
          elements.push(<h1 key={index} className="text-xl md:text-2xl font-bold text-slate-800 mt-6 mb-3 border-b border-slate-200 pb-2">{parseInline(text)}</h1>);
        } else if (depth === 2) {
          elements.push(<h2 key={index} className="text-lg md:text-xl font-bold text-slate-800 mt-5 mb-2.5">{parseInline(text)}</h2>);
        } else {
          elements.push(<h3 key={index} className="text-sm md:text-base font-bold text-slate-800 mt-4 mb-2">{parseInline(text)}</h3>);
        }
        return;
      }

      // Check for bullet list item (e.g. - item, * item)
      const listMatch = line.match(/^[-*]\s+(.+)$/);
      if (listMatch) {
        isListActive = true;
        listItems.push(listMatch[1]);
        return;
      }

      // Non-list line, flush list if it was active
      if (isListActive) {
        flushList(index);
      }

      // Blockquotes (e.g. > Warning)
      if (line.startsWith(">")) {
        const text = line.substring(1).trim();
        elements.push(
          <blockquote key={index} className="pl-4 border-l-4 border-teal-500 italic text-slate-500 my-3 text-sm">
            {parseInline(text)}
          </blockquote>
        );
        return;
      }

      // Plain paragraph line or empty space
      if (line.trim() === "") {
        elements.push(<div key={index} className="h-2" />);
      } else {
        elements.push(
          <p key={index} className="text-slate-600 leading-relaxed text-sm my-2">
            {parseInline(line)}
          </p>
        );
      }
    });

    // Handle open code block at EOF (e.g. when streaming is in progress)
    if (inCodeBlock && codeContent.length > 0) {
      elements.push(
        <CodeBlockComponent
          key="code-eof"
          code={codeContent.join("\n")}
          language={codeLanguage}
        />
      );
    }

    // Flush any trailing list items
    if (isListActive && listItems.length > 0) {
      elements.push(
        <ul key="ul-eof" className="list-disc pl-5 my-3 space-y-1.5 text-slate-700 text-sm">
          {listItems.map((item, idx) => (
            <li key={idx} className="leading-relaxed">{parseInline(item)}</li>
          ))}
        </ul>
      );
    }

    return elements;
  };

  return (
    <div className={`prose prose-slate max-w-none transition-all duration-300 animate-fade-slide-up ${isStreaming ? "streaming-cursor" : ""}`}>
      {renderContent()}
    </div>
  );
};
