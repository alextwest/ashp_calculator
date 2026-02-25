const [buildingSummaryText, setBuildingSummaryText] = useState(DEFAULT_JSON_STRING);
const [userText, setUserText] = useState("");
const [result, setResult] = useState(null);
const [questions, setQuestions] = useState([]);
const [answerText, setAnswerText] = useState("");

async function runRecommend(finalUserText) {
  const building_summary = JSON.parse(buildingSummaryText);

  const res = await fetch("/api/ai/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ building_summary, user_text: finalUserText }),
  }).then(r => r.json());

  setResult(res);
  setQuestions(res.intent?.questions || []);
}