import { Link, useParams } from "react-router-dom";

export default function V2ThankYou() {
  const { token } = useParams();
  return (
    <div className="mx-auto max-w-md px-4 py-16 text-center">
      <h1 className="text-2xl font-semibold">Thank you</h1>
      <p className="mt-2 text-sm text-stone-600">
        Your interview is complete. The hiring team will review your responses.
      </p>
      <Link className="mt-6 inline-block text-sm underline" to={token ? `/v2/i/${token}` : "/v2/test"}>
        Done
      </Link>
    </div>
  );
}
