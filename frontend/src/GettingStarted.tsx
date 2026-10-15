import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, BookOpen, ChevronDown, ChevronUp } from 'lucide-react';

type Role = 'worker' | 'officer' | 'admin' | string;

const workerSteps = [
  { title: 'Check your ASV vials', detail: 'See which batches are verified and ready to issue.', to: '/inventory', action: 'View my ASV vials' },
  { title: 'Request more ASV vials', detail: 'Send a replenishment request to your supply officer.', to: '/replenishment', action: 'View requests' },
];

const officerSteps = [
  { title: 'Review ASV vial alerts', detail: 'Start with facilities that may run low before the next delivery.', to: '/risks', action: 'Open risk alerts' },
  { title: 'Approve worker requests', detail: 'Review facility requests, then record dispatch and confirm delivery.', to: '/approvals', action: 'Review requests' },
  { title: 'Review facility stock', detail: 'Compare ASV vial availability, need, expiry, and usage across your facilities.', to: '/facilities', action: 'Open facilities' },
];

export default function GettingStarted({ role }: { role: Role }) {
  const [collapsed, setCollapsed] = useState(false);
  const isWorker = role === 'worker';
  const steps = isWorker ? workerSteps : officerSteps;
  const heading = isWorker ? 'Getting started at your facility' : 'Your supply officer checklist';

  return (
    <section className="getting-started" aria-labelledby="getting-started-title">
      <div className="getting-started-head">
        <div className="getting-started-title">
          <span className="getting-started-icon"><BookOpen size={17} /></span>
          <div>
            <h2 id="getting-started-title">{heading}</h2>
            <p>{isWorker ? 'Use these steps to keep facility ASV vial information current.' : 'A practical order for reviewing risks, requests, and facility stock.'}</p>
          </div>
        </div>
        <button className="guide-toggle" type="button" aria-expanded={!collapsed} aria-controls="getting-started-steps" onClick={() => setCollapsed(!collapsed)}>
          {collapsed ? 'Show guide' : 'Hide guide'} {collapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
        </button>
      </div>
      {!collapsed && <div className="getting-started-steps" id="getting-started-steps">
        {steps.map((step, index) => (
          <article className="getting-started-step" key={step.title}>
            <span className="getting-started-number">{index + 1}</span>
            <div className="getting-started-copy">
              <h3>{step.title}</h3>
              <p>{step.detail}</p>
              <Link to={step.to}>{step.action} <ArrowRight size={13} /></Link>
            </div>
          </article>
        ))}
      </div>}
    </section>
  );
}
