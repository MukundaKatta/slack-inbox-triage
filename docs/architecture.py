"""Render the slack-inbox-triage architecture diagram as a PNG.

Used as the required "Architecture diagram" upload for the Slack
Agent Builder Challenge Devpost submission.

Run:

    pip install matplotlib
    python3 docs/architecture.py

Output:

    docs/architecture.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt


def main() -> None:
    fig, ax = plt.subplots(figsize=(12, 9))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 9)
    ax.axis("off")

    # Color palette — Slack purple + Gemini blue + governance red.
    SLACK = "#4A154B"
    GEMINI = "#1A73E8"
    GOV = "#C5221F"
    AUDIT = "#137333"
    NEUTRAL = "#37474F"

    def box(x, y, w, h, label, color, text_color="white", fontsize=10):
        ax.add_patch(
            mpatches.FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=0.05",
                facecolor=color,
                edgecolor="black",
                linewidth=1.2,
            )
        )
        ax.text(
            x + w / 2,
            y + h / 2,
            label,
            ha="center",
            va="center",
            color=text_color,
            fontsize=fontsize,
            fontweight="bold",
            wrap=True,
        )

    def arrow(x1, y1, x2, y2, label="", curve=False):
        style = "arc3,rad=0.2" if curve else "arc3,rad=0"
        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops=dict(arrowstyle="->", color="black", lw=1.4, connectionstyle=style),
        )
        if label:
            ax.text(
                (x1 + x2) / 2,
                (y1 + y2) / 2 + 0.12,
                label,
                ha="center",
                va="bottom",
                color="black",
                fontsize=8,
                style="italic",
            )

    # Title
    ax.text(
        6,
        8.6,
        "slack-inbox-triage — governance-first agent architecture",
        ha="center",
        fontsize=14,
        fontweight="bold",
    )

    # Row 1 — User + Slack platform
    box(0.5, 7.2, 2.5, 1.0, "Workspace user\n/triage #channel", SLACK)
    box(4.5, 7.2, 3.0, 1.0, "Slack platform\n(slash command + OAuth scopes)", SLACK)
    box(9.0, 7.2, 2.5, 1.0, "Slack manifest\n(5 scopes only)", SLACK)
    arrow(3.0, 7.7, 4.5, 7.7)
    arrow(7.5, 7.7, 9.0, 7.7, curve=True)

    # Row 2 — Scope allowlist (governance gate 1)
    box(4.5, 5.7, 3.0, 1.0, "ScopeAllowlist\n(refuses out-of-manifest call)", GOV)
    arrow(6.0, 7.2, 6.0, 6.7)
    arrow(9.0, 7.5, 7.5, 6.4, curve=True)

    # Row 3 — Slack client + classifier
    box(0.5, 4.0, 2.5, 1.2, "SlackClient\n(conversations.history,\nchat.postMessage)", NEUTRAL)
    box(4.5, 4.0, 3.0, 1.2, "Classifier\nGemini 2.5 Flash Lite\n+ heuristic fallback", GEMINI)
    box(9.0, 4.0, 2.5, 1.2, "ToolArg validator\n(channel + text shape,\ncaps + types)", GOV)
    arrow(6.0, 5.7, 6.0, 5.2)
    arrow(4.5, 4.6, 3.0, 4.6)
    arrow(7.5, 4.6, 9.0, 4.6)

    # Row 4 — Schema repair + egress
    box(4.5, 2.4, 3.0, 1.0, "SchemaRepair\n(parse fenced JSON,\nclamp confidence)", GEMINI)
    box(9.0, 2.4, 2.5, 1.0, "EgressAllowlist\n(any HTTP host)", GOV)
    arrow(6.0, 4.0, 6.0, 3.4)
    arrow(7.5, 2.9, 9.0, 2.9)

    # Row 5 — Audit + reply
    box(0.5, 0.6, 3.5, 1.2, "AuditTrail (JSONL, append-only)\nscope_denied | egress_blocked\ntool_arg_error | classify_repaired", AUDIT)
    box(5.0, 0.6, 3.0, 1.2, "Ephemeral reply\n4-intent triage report\n+ drafted replies", SLACK)
    arrow(4.5, 2.9, 4.0, 1.8, curve=True)
    arrow(9.0, 2.9, 4.0, 1.5, curve=True)
    arrow(4.5, 2.4, 6.0, 1.8)

    # Legend
    legend_y = 0.05
    ax.add_patch(mpatches.Rectangle((0.5, legend_y), 0.3, 0.2, facecolor=SLACK, edgecolor="black"))
    ax.text(0.9, legend_y + 0.1, "Slack", va="center", fontsize=9)
    ax.add_patch(mpatches.Rectangle((2.0, legend_y), 0.3, 0.2, facecolor=GEMINI, edgecolor="black"))
    ax.text(2.4, legend_y + 0.1, "Model layer", va="center", fontsize=9)
    ax.add_patch(mpatches.Rectangle((4.0, legend_y), 0.3, 0.2, facecolor=GOV, edgecolor="black"))
    ax.text(4.4, legend_y + 0.1, "Governance gate", va="center", fontsize=9)
    ax.add_patch(mpatches.Rectangle((6.5, legend_y), 0.3, 0.2, facecolor=AUDIT, edgecolor="black"))
    ax.text(6.9, legend_y + 0.1, "Audit trail", va="center", fontsize=9)

    out = Path(__file__).resolve().parent / "architecture.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
