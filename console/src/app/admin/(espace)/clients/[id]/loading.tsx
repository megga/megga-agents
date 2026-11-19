import { AttentePage } from "@/components/admin/attente";

// Entre les onglets d'un client, l'en-tête du client reste en place : seule la suite attend.
export default function Attente() {
  return <AttentePage titre={false} />;
}
