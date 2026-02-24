"""
GitLab Security Scanner Agent
AI-powered security vulnerability detection using Claude
"""

import os
import re
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from openai import OpenAI


class Severity(Enum):
    """Vulnerability severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class SecurityFinding:
    """Represents a security vulnerability finding"""
    id: str
    title: str
    description: str
    severity: Severity
    cwe_id: Optional[str]
    file_path: str
    line_number: int
    vulnerable_code: str
    fix_recommendation: str
    business_impact: str
    false_positive_likelihood: float
    exploit_scenario: Optional[str] = None
    compliance_violations: List[str] = None
    
    def __post_init__(self):
        if self.compliance_violations is None:
            self.compliance_violations = []
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['severity'] = self.severity.value
        return data


class SecurityScanner:
    """Main security scanner implementation"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize security scanner with AI analysis
        
        Args:
            api_key: API key for AI provider (defaults to VENICE_API_KEY or OPENAI_API_KEY env var)
        """
        self.api_key = api_key or os.environ.get("VENICE_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("AI API key required (set VENICE_API_KEY or OPENAI_API_KEY)")
        
        # Auto-detect provider
        is_venice = not self.api_key.startswith("sk-")
        base_url = "https://api.venice.ai/api/v1" if is_venice else None
        self.model = "venice-uncensored" if is_venice else "gpt-4o"
        self.client = OpenAI(api_key=self.api_key, base_url=base_url)
        self.findings: List[SecurityFinding] = []
        
        # Vulnerability patterns
        self.patterns = self._load_vulnerability_patterns()
        
    def _load_vulnerability_patterns(self) -> Dict[str, Any]:
        """Load vulnerability detection patterns"""
        return {
            "sql_injection": {
                "patterns": [
                    r"execute\([\"'].*?\+.*?[\"']\)",
                    r"execute\(f[\"'].*?{.*?}.*?[\"']\)",
                    r"cursor\.execute\([^?]*\+",
                ],
                "cwe": "CWE-89",
                "severity": Severity.HIGH,
                "description": "SQL Injection vulnerability detected"
            },
            "xss": {
                "patterns": [
                    r"innerHTML\s*=",
                    r"document\.write\(",
                    r"eval\(",
                ],
                "cwe": "CWE-79",
                "severity": Severity.MEDIUM,
                "description": "Cross-Site Scripting (XSS) vulnerability"
            },
            "hardcoded_secrets": {
                "patterns": [
                    r"(?i)(api[_-]?key|password|secret|token)\s*=\s*['\"][^'\"]{8,}['\"]",
                    r"(?i)aws[_-]?(access|secret)[_-]?key\s*=",
                    r"(?i)private[_-]?key\s*=\s*['\"]",
                ],
                "cwe": "CWE-798",
                "severity": Severity.CRITICAL,
                "description": "Hardcoded secrets detected"
            },
            "command_injection": {
                "patterns": [
                    r"os\.system\(",
                    r"subprocess\.call\([^,]*\+",
                    r"exec\(",
                ],
                "cwe": "CWE-78",
                "severity": Severity.HIGH,
                "description": "Command injection vulnerability"
            },
            "insecure_random": {
                "patterns": [
                    r"import random(?!\s+as\s+secrets)",
                    r"Math\.random\(\)",
                ],
                "cwe": "CWE-330",
                "severity": Severity.MEDIUM,
                "description": "Insecure random number generation"
            },
        }
    
    def scan_file(self, file_path: str, content: str) -> List[SecurityFinding]:
        """
        Scan a single file for vulnerabilities
        
        Args:
            file_path: Path to the file
            content: File content
            
        Returns:
            List of security findings
        """
        findings = []
        lines = content.split('\n')
        
        # Pattern-based detection
        for vuln_type, config in self.patterns.items():
            for pattern in config["patterns"]:
                for line_num, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        finding = SecurityFinding(
                            id=f"{vuln_type}_{file_path}_{line_num}",
                            title=config["description"],
                            description=f"Potential {vuln_type} vulnerability",
                            severity=config["severity"],
                            cwe_id=config["cwe"],
                            file_path=file_path,
                            line_number=line_num,
                            vulnerable_code=line.strip(),
                            fix_recommendation="Pending AI analysis",
                            business_impact="Pending AI analysis",
                            false_positive_likelihood=0.5
                        )
                        findings.append(finding)
        
        return findings
    
    def analyze_with_claude(
        self,
        findings: List[SecurityFinding],
        code_context: str
    ) -> List[SecurityFinding]:
        """
        Enhance findings with Claude AI analysis
        
        Args:
            findings: Initial findings from pattern matching
            code_context: Surrounding code context
            
        Returns:
            Enhanced findings with AI insights
        """
        if not findings:
            return []
        
        # Prepare findings for Claude
        findings_summary = "\n\n".join([
            f"Finding {i+1}:\n"
            f"Type: {f.title}\n"
            f"File: {f.file_path}:{f.line_number}\n"
            f"Code: {f.vulnerable_code}\n"
            for i, f in enumerate(findings)
        ])
        
        prompt = f"""Analyze these security findings in context:

{findings_summary}

Code Context:
```
{code_context}
```

For each finding, provide:
1. Is this a true vulnerability or false positive? (confidence 0-1)
2. Actual severity (critical/high/medium/low/info)
3. Business impact explanation
4. Specific fix recommendation with code example
5. Exploitation scenario if applicable

Respond in JSON format:
{{
  "findings": [
    {{
      "finding_id": 1,
      "is_vulnerability": true,
      "confidence": 0.95,
      "severity": "high",
      "business_impact": "...",
      "fix_recommendation": "...",
      "exploit_scenario": "..."
    }}
  ]
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": "You are a security expert. Always respond with valid JSON only, no markdown."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse AI response (strip markdown code blocks if present)
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                raw = raw.rsplit("```", 1)[0].strip()
            result = json.loads(raw)
            
            # Update findings with AI analysis
            for i, finding_analysis in enumerate(result.get("findings", [])):
                if i < len(findings):
                    finding = findings[i]
                    
                    # Update with AI insights
                    if not finding_analysis.get("is_vulnerability", True):
                        finding.false_positive_likelihood = 1.0 - finding_analysis.get("confidence", 0.5)
                    else:
                        finding.false_positive_likelihood = 1.0 - finding_analysis.get("confidence", 0.5)
                        finding.severity = Severity(finding_analysis.get("severity", "medium"))
                        finding.business_impact = finding_analysis.get("business_impact", "")
                        finding.fix_recommendation = finding_analysis.get("fix_recommendation", "")
                        finding.exploit_scenario = finding_analysis.get("exploit_scenario")
            
        except Exception as e:
            print(f"Claude analysis failed: {e}")
            # Continue with original findings
        
        # Filter out likely false positives
        return [f for f in findings if f.false_positive_likelihood < 0.7]
    
    def scan_repository(
        self,
        files: Dict[str, str],
        use_ai: bool = True
    ) -> List[SecurityFinding]:
        """
        Scan multiple files in repository
        
        Args:
            files: Dict of file_path -> content
            use_ai: Whether to use Claude AI analysis
            
        Returns:
            List of all security findings
        """
        all_findings = []
        
        for file_path, content in files.items():
            findings = self.scan_file(file_path, content)
            
            if findings and use_ai:
                # Get surrounding context
                context = content
                findings = self.analyze_with_claude(findings, context)
            
            all_findings.extend(findings)
        
        self.findings = all_findings
        return all_findings
    
    def generate_report(self, format: str = "markdown") -> str:
        """
        Generate security report
        
        Args:
            format: Report format (markdown, json, html)
            
        Returns:
            Formatted report
        """
        if format == "json":
            return json.dumps([f.to_dict() for f in self.findings], indent=2)
        
        elif format == "markdown":
            # Count by severity
            severity_counts = {s: 0 for s in Severity}
            for f in self.findings:
                severity_counts[f.severity] += 1
            
            report = "# Security Scan Report\n\n"
            report += "## Summary\n\n"
            report += f"- 🔴 Critical: {severity_counts[Severity.CRITICAL]}\n"
            report += f"- 🟠 High: {severity_counts[Severity.HIGH]}\n"
            report += f"- 🟡 Medium: {severity_counts[Severity.MEDIUM]}\n"
            report += f"- 🔵 Low: {severity_counts[Severity.LOW]}\n"
            report += f"- ℹ️ Info: {severity_counts[Severity.INFO]}\n\n"
            
            report += "## Findings\n\n"
            
            for finding in sorted(self.findings, key=lambda x: list(Severity).index(x.severity)):
                emoji = {
                    Severity.CRITICAL: "🔴",
                    Severity.HIGH: "🟠",
                    Severity.MEDIUM: "🟡",
                    Severity.LOW: "🔵",
                    Severity.INFO: "ℹ️"
                }[finding.severity]
                
                report += f"### {emoji} {finding.title}\n\n"
                report += f"**Severity:** {finding.severity.value.upper()}\n"
                report += f"**CWE:** {finding.cwe_id}\n"
                report += f"**Location:** `{finding.file_path}:{finding.line_number}`\n\n"
                
                report += f"**Vulnerable Code:**\n```\n{finding.vulnerable_code}\n```\n\n"
                
                report += f"**Business Impact:**\n{finding.business_impact}\n\n"
                
                if finding.exploit_scenario:
                    report += f"**Exploit Scenario:**\n{finding.exploit_scenario}\n\n"
                
                report += f"**Fix Recommendation:**\n{finding.fix_recommendation}\n\n"
                
                if finding.compliance_violations:
                    report += f"**Compliance Violations:**\n"
                    for violation in finding.compliance_violations:
                        report += f"- {violation}\n"
                    report += "\n"
                
                report += "---\n\n"
            
            return report
        
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get scan statistics"""
        severity_counts = {s.value: 0 for s in Severity}
        for f in self.findings:
            severity_counts[f.severity.value] += 1
        
        return {
            "total_findings": len(self.findings),
            "by_severity": severity_counts,
            "high_or_critical": severity_counts["critical"] + severity_counts["high"],
            "files_affected": len(set(f.file_path for f in self.findings)),
            "avg_false_positive_likelihood": sum(f.false_positive_likelihood for f in self.findings) / len(self.findings) if self.findings else 0
        }


# Example usage
if __name__ == "__main__":
    # Example vulnerable code
    test_files = {
        "app.py": '''
def get_user(username):
    query = f"SELECT * FROM users WHERE username = '{username}'"
    return db.execute(query)

api_key = "sk_live_1234567890abcdef"

def run_command(cmd):
    os.system(cmd)
'''
    }
    
    scanner = SecurityScanner()
    findings = scanner.scan_repository(test_files, use_ai=True)
    
    print(scanner.generate_report("markdown"))
    print("\nStatistics:", json.dumps(scanner.get_statistics(), indent=2))
