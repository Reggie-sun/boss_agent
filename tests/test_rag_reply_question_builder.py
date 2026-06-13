from boss_agent_cli.rag_reply.question_builder import build_answer_objective, build_rag_question


def test_question_builder_excludes_full_boss_context():
	question = build_rag_question(
		"你这个RAG项目具体做了什么？",
		"后端 Python/FastAPI，企业知识库问答。",
		build_answer_objective("project_question"),
	)
	assert "HR question:" in question
	assert "Short job summary:" in question
	assert "raw_json" not in question
	assert "完整职位详情" not in question
	assert "recruiter profile" not in question.lower()

