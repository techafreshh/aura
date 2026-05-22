import type { FinalReport } from "@/api/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { CheckCircle, AlertCircle, Download } from "lucide-react";
import { jsPDF } from "jspdf";

interface ReportViewProps {
  report: FinalReport;
  onDone: () => void;
}

export function ReportView({ report, onDone }: ReportViewProps) {
  const getRecommendationColor = (rec: string) => {
    switch (rec) {
      case "Strong Hire": return "bg-green-600";
      case "Hire": return "bg-green-500";
      case "Hold": return "bg-yellow-500";
      case "No Hire": return "bg-red-500";
      default: return "bg-gray-500";
    }
  };

  const handleDownload = () => {
    const doc = new jsPDF();
    const pageWidth = doc.internal.pageSize.getWidth();
    const margin = 20;
    const maxWidth = pageWidth - margin * 2;
    let y = 20;

    const addText = (text: string, size: number, bold = false) => {
      doc.setFontSize(size);
      doc.setFont("helvetica", bold ? "bold" : "normal");
      const lines = doc.splitTextToSize(text, maxWidth);
      if (y + lines.length * size * 0.5 > 270) {
        doc.addPage();
        y = 20;
      }
      doc.text(lines, margin, y);
      y += lines.length * size * 0.5 + 4;
    };

    addText("INTERVIEW REPORT", 18, true);
    y += 4;
    addText(`Candidate: ${report.candidate_name}`, 12);
    addText(`Overall Score: ${report.overall_score}/100`, 12);
    addText(`Recommendation: ${report.recommendation}`, 12);
    y += 6;

    addText("Summary", 14, true);
    addText(report.summary, 10);
    y += 4;

    addText("Section Grades", 14, true);
    for (const s of report.section_grades) {
      addText(`${s.section_name}: ${s.score}/10 — ${s.comments}`, 10);
    }
    y += 4;

    addText("Strengths", 14, true);
    for (const s of report.strengths) {
      addText(`• ${s}`, 10);
    }
    y += 4;

    addText("Areas for Improvement", 14, true);
    for (const w of report.weaknesses) {
      addText(`• ${w}`, 10);
    }

    doc.save(`interview-report-${report.candidate_name.replace(/\s+/g, "-").toLowerCase()}.pdf`);
  };

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold">Interview Result</h1>
        <Badge className={`${getRecommendationColor(report.recommendation)} text-white text-lg px-4 py-1`}>
          {report.recommendation}
        </Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Candidate: {report.candidate_name}</CardTitle>
            <CardDescription>Overall Performance Summary</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground leading-relaxed">
              {report.summary}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Overall Score</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-center justify-center space-y-4">
            <div className="text-5xl font-bold text-primary">{report.overall_score}%</div>
            <Progress value={report.overall_score} className="w-full" />
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle className="text-green-500" /> Key Strengths
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc list-inside space-y-2">
              {report.strengths.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertCircle className="text-yellow-500" /> Areas for Improvement
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc list-inside space-y-2">
              {report.weaknesses.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Section Breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {report.section_grades.map((section, i) => (
              <div key={i} className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span>{section.section_name}</span>
                  <span className="font-medium">{section.score}/10</span>
                </div>
                <Progress value={section.score * 10} />
                <p className="text-xs text-muted-foreground">{section.comments}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-center gap-4 pt-6">
        <button
          onClick={handleDownload}
          className="flex items-center gap-2 border border-primary text-primary hover:bg-primary/10 px-8 py-2 rounded-md transition-colors"
        >
          <Download className="h-4 w-4" /> Download Report
        </button>
        <button 
          onClick={onDone}
          className="bg-primary text-primary-foreground hover:bg-primary/90 px-8 py-2 rounded-md transition-colors"
        >
          Back to Start
        </button>
      </div>
    </div>
  );
}
