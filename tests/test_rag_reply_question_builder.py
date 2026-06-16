from boss_agent_cli.rag_reply.question_builder import build_answer_objective, build_rag_question


def test_question_builder_excludes_full_boss_context():
	question = build_rag_question(
		"你这个RAG项目具体做了什么？",
		"后端 Python/FastAPI，企业知识库问答。",
		build_answer_objective("project_question", "你这个RAG项目具体做了什么？"),
	)
	assert "问题：" in question
	assert "岗位摘要：" in question
	assert "候选人面试交流" in question
	assert "raw_json" not in question
	assert "完整职位详情" not in question
	assert "recruiter profile" not in question.lower()


def test_salary_objective_asks_rag_for_uploaded_salary_facts():
	objective = build_answer_objective("salary_or_offer", "本人薪资和期望薪资是多少？")

	assert "当前薪资和期望薪资" in objective
	assert "不要推测" in objective
