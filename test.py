def solution(s):
    st=[]
    result=[]
    cur=[]
    for i in range(len(s)):
        # {没有入cur
        if s[i]=='{':
            st.append(s[i])
            cur.append(s[i])
        elif s[i]=='}':
            st.pop()
            cur.append(s[i])
            if len(st)==0:
                result.append("".join(cur))
                cur=[]
        else:
                cur.append(s[i])
    return result

