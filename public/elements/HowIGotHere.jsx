import { useState } from "react";
import { ChevronDown, ChevronRight, Database, Lock, Clock, Search } from "lucide-react";

// Collapsible "how I got here" panel shown under each answer. Props come from chainlit_app.py.
export default function HowIGotHere() {
  const [open, setOpen] = useState(false);
  const steps = props.steps || [];
  const sources = props.sources || [];

  return (
    <div className="em-how">
      <button className="em-how-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        Detalhes desta resposta
      </button>
      {open && (
        <div className="em-how-panel">
          <div className="em-how-row">
            <span className="em-how-key"><Search size={13} /> Consultas</span>
            <div className="em-how-val">
              {steps.length === 0 && <span>Nenhuma consulta: respondido pelas regras de atendimento.</span>}
              {steps.map((step, i) => (
                <div key={i} className="em-how-step">
                  <span>{i + 1}. {step.label}</span>
                  {step.filters.map((f, j) => (
                    <code key={j} className="em-chip">{f}</code>
                  ))}
                </div>
              ))}
            </div>
          </div>
          {sources.length > 0 && (
            <div className="em-how-row">
              <span className="em-how-key"><Database size={13} /> Fontes</span>
              <div className="em-how-val">
                {sources.map((s, i) => (
                  <code key={i} className="em-chip">{s}</code>
                ))}
              </div>
            </div>
          )}
          <div className="em-how-row">
            <span className="em-how-key"><Clock size={13} /> Dados de</span>
            <div className="em-how-val">{props.dataFrom}</div>
          </div>
          <div className="em-how-row">
            <span className="em-how-key"><Lock size={13} /> Acesso</span>
            <div className="em-how-val">{props.access}</div>
          </div>
        </div>
      )}
    </div>
  );
}
