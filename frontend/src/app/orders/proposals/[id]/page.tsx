import { ProposalDetail } from "@/components/OrderReview";
export default function Page({params}: {params: {id: string}}) { return <ProposalDetail id={params.id}/>; }
