import { Check } from 'lucide-react';

export type DeliveryStep={label:string;state:'complete'|'current'|'upcoming';timestamp?:string|null};

export default function DeliveryTimeline({steps}:{steps:DeliveryStep[]}){
  return <ol className="delivery-timeline" aria-label="Delivery progress">
    {steps.map((step,index)=><li className={`delivery-timeline-step ${step.state}`} key={`${step.label}-${index}`}>
      <span className="delivery-timeline-marker" aria-hidden="true">{step.state==='complete'?<Check size={12}/>:index+1}</span>
      <span className="delivery-timeline-copy"><b>{step.label}</b>{step.timestamp&&<time dateTime={step.timestamp}>{new Date(step.timestamp).toLocaleString()}</time>}</span>
    </li>)}
  </ol>;
}
