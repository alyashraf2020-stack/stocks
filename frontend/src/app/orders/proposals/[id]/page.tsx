import { ProposalDetail } from "@/components/OrderReview";
export default async function Page({ params }: PageProps<"/orders/proposals/[id]">) {
  const { id } = await params;
  return <ProposalDetail key={id} id={id} />;
}
