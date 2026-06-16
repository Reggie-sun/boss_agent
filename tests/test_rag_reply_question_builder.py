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
