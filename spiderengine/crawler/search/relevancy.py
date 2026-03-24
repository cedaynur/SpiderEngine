"""Text-matching and frequency-based scoring."""


class RelevancyScorer:
    """Scores documents against a query for result ordering."""

    @staticmethod
    def calculate_score(query: str, url: str, depth: int, frequency: int) -> float:
        # 1. Temel Frekans Puanı (Her kelime geçişi için 20 puan)
        freq_score = frequency * 20
        
        # 2. URL Bonusu (Kelime URL içinde geçiyorsa +100 puan)
        url_bonus = 100 if query.lower() in url.lower() else 0
        
        # 3. Derinlik Cezası (Ana sayfadan uzaklaştıkça her adımda -10 puan)
        depth_penalty = depth * 10
        
        # Toplam Skor
        return freq_score + url_bonus - depth_penalty

    def rank_results(self, query: str, raw_hits: list) -> list:
        # Gelen ham sonuçları (hits) bizim formülümüze göre sıralar
        scored_hits = []
        for hit in raw_hits:
            # hit: (url, origin_url, depth, frequency) varsayalım
            url, origin, depth, freq = hit
            score = self.calculate_score(query, url, depth, freq)
            scored_hits.append((url, origin, depth, score))
            
        # Skorlara göre büyükten küçüğe sırala
        return sorted(scored_hits, key=lambda x: x[3], reverse=True)
        pass
