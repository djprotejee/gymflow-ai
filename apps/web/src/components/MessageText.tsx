import type React from "react";

function cleanAssistantText(value: string) {
  return value
    .replace(/\s+\*\s+/g, "\n- ")
    .split("\n")
    .filter((line) => !line.toLowerCase().includes("locally seeded"))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function renderInlineMarkdown(value: string) {
  const nodes: React.ReactNode[] = [];
  const pattern = /(\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)|\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(value)) !== null) {
    if (match.index > cursor) {
      nodes.push(value.slice(cursor, match.index));
    }
    if (match[2] && match[3]) {
      nodes.push(
        <a href={match[3]} target="_blank" rel="noreferrer" key={`${match.index}-link`}>
          {match[2]}
        </a>,
      );
    } else if (match[4]) {
      nodes.push(<strong key={`${match.index}-bold`}>{match[4]}</strong>);
    } else if (match[5]) {
      nodes.push(<em key={`${match.index}-italic`}>{match[5]}</em>);
    } else if (match[6]) {
      nodes.push(<code key={`${match.index}-code`}>{match[6]}</code>);
    }
    cursor = match.index + match[0].length;
  }
  if (cursor < value.length) {
    nodes.push(value.slice(cursor));
  }
  return nodes.length ? nodes : value;
}

function splitTableRow(row: string) {
  return row
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isTableSeparator(line: string) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

// Render the coach's Markdown subset without allowing arbitrary HTML.
export function MessageText({ text }: { text: string }) {
  const lines = cleanAssistantText(text).split("\n");
  const blocks: React.ReactNode[] = [];
  let index = 0;
  let blockIndex = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    if (/^#{1,6}\s+/.test(line)) {
      blocks.push(<h4 key={`heading-${blockIndex++}`}>{renderInlineMarkdown(line.replace(/^#{1,6}\s+/, ""))}</h4>);
      index += 1;
      continue;
    }

    if (line.includes("|") && lines[index + 1] && isTableSeparator(lines[index + 1])) {
      const header = splitTableRow(line);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }
      blocks.push(
        <div className="message-table-wrap" key={`table-${blockIndex++}`}>
          <table className="message-table">
            <thead>
              <tr>{header.map((cell) => <th key={cell}>{renderInlineMarkdown(cell)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={`row-${rowIndex}`}>
                  {row.map((cell, cellIndex) => <td key={`${rowIndex}-${cellIndex}`}>{renderInlineMarkdown(cell)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (/^([-*]|\d+\.)\s+/.test(line)) {
      const items: string[] = [];
      const ordered = /^\d+\.\s+/.test(line);
      while (index < lines.length && (ordered ? /^\d+\.\s+/.test(lines[index].trim()) : /^[-*]\s+/.test(lines[index].trim()))) {
        items.push(lines[index].trim().replace(/^([-*]|\d+\.)\s+/, ""));
        index += 1;
      }
      const ListTag = ordered ? "ol" : "ul";
      blocks.push(
        <ListTag key={`list-${blockIndex++}`}>
          {items.map((item) => <li key={item}>{renderInlineMarkdown(item)}</li>)}
        </ListTag>,
      );
      continue;
    }

    const paragraph: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^#{1,6}\s+/.test(lines[index].trim()) &&
      !/^([-*]|\d+\.)\s+/.test(lines[index].trim()) &&
      !(lines[index].includes("|") && lines[index + 1] && isTableSeparator(lines[index + 1]))
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p key={`paragraph-${blockIndex++}`}>{renderInlineMarkdown(paragraph.join(" "))}</p>);
  }

  return <>{blocks}</>;
}
